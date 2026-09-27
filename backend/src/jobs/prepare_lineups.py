"""Offline full-position ESPN preparation. --train is explicit, never a weekly default."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text

from src.api.player_service import evidence_models
from src.core.config import get_settings
from src.core.database import SessionLocal
from src.data.ingestion import download_snapshot, sha256, write_json
from src.data.lineup_data import load_inputs, supplement
from src.db.models import LineupSnapshot, PlayerGameCompletionEvidence
from src.domain.espn import POSITIONS, SCORING_VERSION
from src.features.lineup_features import FEATURE_VERSION, FeatureIndex
from src.jobs.publication_checks import CoverageError, coverage_report, target_week
from src.models.lineup_model import predict, train_and_evaluate


def prepare(
    inputs: dict, model: dict, evidence: list, season: int, week: int, now: datetime
) -> dict:
    if model["scoring_version"] != SCORING_VERSION or model["feature_version"] != FEATURE_VERSION:
        raise ValueError("Model scoring or feature version mismatch")
    target = [g for g in inputs["games"] if (g["season"], g["week"]) == (season, week)]
    if not target or any(
        not g["game_datetime"] or g["game_datetime"] <= now or g["game_status"] != "upcoming"
        for g in target
    ):
        raise ValueError("Lineup preparation requires a fully upcoming scheduled week")
    matchups = {}
    for g in target:
        for team, opponent in ((g["home_team"], g["away_team"]), (g["away_team"], g["home_team"])):
            matchups[team] = {
                "opponent": opponent,
                "home": team == g["home_team"],
                "kickoff": g["game_datetime"].isoformat(),
            }
    latest = {}
    conflicts = set()
    for r in sorted(inputs["rosters"], key=lambda r: r["week"]):
        if (
            r["season"] != season
            or r["week"] > week
            or r["game_type"] != "REG"
            or not r["gsis_id"]
            or r["position"] not in POSITIONS
        ):
            continue
        pid = r["gsis_id"]
        old = latest.get(pid)
        if old and old["week"] == r["week"] and old["team"] != r["team"]:
            conflicts.add(pid)
        elif not old or old["week"] < r["week"]:
            conflicts.discard(pid)
        latest[pid] = r
    candidates = [
        {
            "id": pid,
            "name": r["full_name"],
            "position": r["position"],
            "team": None if pid in conflicts else r["team"],
            "roster_week": r["week"],
            "roster_status": r["status"],
        }
        for pid, r in latest.items()
    ]
    all_teams = {
        g[k] for g in inputs["games"] if g["season"] == season for k in ("home_team", "away_team")
    }
    candidates += [
        {
            "id": f"DST:{team}",
            "name": f"{team} D/ST",
            "position": "DST",
            "team": team,
            "roster_week": week,
            "roster_status": "TEAM",
        }
        for team in sorted(all_teams)
    ]
    index = FeatureIndex(inputs["rows"], evidence)
    for p in candidates:
        matchup = matchups.get(p["team"])
        features = index.build(
            p["id"], p["position"], matchup["opponent"] if matchup else None, season, week, now
        )
        reason = (
            "Ambiguous team assignment"
            if p["team"] is None
            else "Bye week / no scheduled game"
            if matchup is None
            else f"Roster status: {p['roster_status']} (not active)"
            if p["roster_status"] not in ("ACT", "TEAM")
            else features["unavailable_reason"]
        )
        estimated = predict(model["models"][p["position"]], features) if not reason else None
        p.update(
            matchup=matchup,
            projection=round(estimated, 4) if estimated is not None else None,
            unavailable_reason=reason,
            features={k: v for k, v in features.items() if k != "vector"},
            model_kind=model["models"][p["position"]]["kind"],
            availability="Team unit"
            if p["position"] == "DST"
            else "Participation unconfirmed — verify injury reports before kickoff",
        )
    return {
        "snapshot_id": uuid4().hex,
        "season": season,
        "week": week,
        "generated_at": now.isoformat(),
        "data_as_of": inputs["as_of"],
        "supplement_as_of": inputs["supplement_as_of"],
        "first_kickoff": min(g["game_datetime"] for g in target).isoformat(),
        "scoring_version": SCORING_VERSION,
        "feature_version": FEATURE_VERSION,
        "model_version": model["version"],
        "artifact_id": inputs["artifact"],
        "model_report": model["report"],
        "evaluation_note": model["evaluation_note"],
        "audit": inputs["audit"],
        "players": sorted(candidates, key=lambda p: p["name"]),
        "notice": "Estimates assume participation. No live injury feed. Latest active roster "
        "does not confirm game-day availability. Confirm your ESPN scoring settings.",
    }


def run(snapshot: Path | None, season: int, week: int | None, train: bool) -> dict:
    settings = get_settings()
    root = snapshot or download_snapshot(list(range(2024, season + 1)), settings.data_dir)
    supplement(root, list(range(2024, season + 1)))
    inputs = load_inputs(root)
    now = datetime.now(UTC)
    intended = target_week(inputs["games"], season, now)
    if week is not None and week != intended:
        raise ValueError("Requested week differs from this publication period's intended week")
    week = intended
    with SessionLocal() as session:
        evidence = evidence_models(
            session.scalars(
                select(PlayerGameCompletionEvidence).where(
                    PlayerGameCompletionEvidence.reviewed_at <= now
                )
            ).all()
        )
    model_path = settings.model_dir / "lineup-model-v1.json"
    if train:
        if model_path.exists():
            raise ValueError(
                "Model already exists. Version a new experiment; do not retune the holdout"
            )
        model = train_and_evaluate(inputs, evidence)
        write_json(model_path, model)
    else:
        if not model_path.exists():
            raise ValueError("Train and evaluate once with --train before weekly preparation")
        model = json.loads(model_path.read_text())
    payload = prepare(inputs, model, evidence, season, week, now)
    payload["model_sha256"] = sha256(model_path)
    report = coverage_report(inputs, payload, now)
    write_json(
        settings.data_dir / "lineups" / payload["snapshot_id"] / "coverage-report.json", report
    )
    if report["errors"]:
        raise CoverageError(report)
    payload["coverage"] = report
    # Persist the exact prepared inputs for reproducibility, apart from raw source files.
    artifact = settings.data_dir / "lineups" / payload["snapshot_id"]
    write_json(artifact / "inputs.json", inputs)
    write_json(artifact / "completion-evidence.json", [e.model_dump(mode="json") for e in evidence])
    write_json(artifact / "model.json", model)
    write_json(artifact / "snapshot.json", payload)
    with SessionLocal() as session, session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(174202410)"))
        if datetime.fromisoformat(payload["first_kickoff"]) <= datetime.now(UTC):
            raise ValueError("Week started during preparation; snapshot not saved")
        session.add(
            LineupSnapshot(
                snapshot_id=payload["snapshot_id"],
                season=season,
                week=week,
                generated_at=now,
                payload=payload,
            )
        )
    return {
        "snapshot": str(root),
        "snapshot_id": payload["snapshot_id"],
        "artifact_dir": str(artifact),
        "season": season,
        "week": week,
        "players": len(payload["players"]),
        "projected": {
            pos: sum(
                p["position"] == pos and p["projection"] is not None for p in payload["players"]
            )
            for pos in POSITIONS
        },
        "model_report": model["report"],
        "audit": inputs["audit"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--week", type=int)
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.snapshot, args.season, args.week, args.train), indent=2))


if __name__ == "__main__":
    main()
