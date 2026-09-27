from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.domain.completion import CompletionEvidence, completion_at
from src.features.player_history import build_player_history
from src.models.baseline import predict_baseline

CUTOFF = datetime(2026, 9, 15, 12, tzinfo=UTC)


def evidence(game_id, status="finished", published=None):
    published = published or datetime(2026, 9, 10, tzinfo=UTC)
    return CompletionEvidence(
        player_id="player",
        game_id=game_id,
        status=status,
        source_url="https://www.nfl.com/news/test-fixture",
        source_published_at=published,
        retrieved_at=published,
        reviewed_at=published,
        evidence_note="Synthetic test fixture; not a real report.",
        reviewer="test",
    )


def history():
    return [
        dict(
            player_id="player",
            game_id=f"game{i}",
            season=2025,
            week=i,
            game_type="REG",
            game_datetime=datetime(2025, 9, i + 1, tzinfo=UTC),
            fantasy_points_ppr=score,
            targets=i,
            receptions=i,
            carries=0,
            rushing_yards=0,
            receiving_yards=i * 10,
            rushing_tds=0,
            receiving_tds=0,
        )
        for i, score in enumerate([10, 0, 8, 6, 100], 1)
    ]


def build(stats=None, reviews=None, participation=None, season=2026, week=2, cutoff=CUTOFF):
    stats = history() if stats is None else stats
    return build_player_history(
        player_id="player",
        position="WR",
        season=season,
        week=week,
        cutoff=cutoff,
        stats=stats,
        participation=participation or [],
        evidence=reviews if reviews is not None else [evidence(r["game_id"]) for r in stats],
    )


def test_dnf_is_skipped_zero_point_finished_game_counts():
    reviews = [evidence(f"game{i}", "dnf" if i == 5 else "finished") for i in range(1, 6)]
    features = build(reviews=reviews)
    assert features["games_played_prior"] == 5
    assert features["eligible_games_prior"] == 4
    assert features["excluded_dnf_games"] == 1
    assert predict_baseline(features) == 6
    assert features["ppr_points_prev"] == 100  # Actual previous outcome is preserved.


def test_no_report_does_not_block_average_or_fabricate_finished_status():
    features = build(reviews=[])
    assert predict_baseline(features) == 28.5
    assert features["unavailable_reason"] is None
    assert features["unknown_completion_games"] == 5
    assert completion_at([], "player", "game1", CUTOFF) == "unknown"


def test_target_week_outcome_does_not_change_features():
    stats = history()
    reviews = [evidence(r["game_id"]) for r in stats]
    before = build(stats=stats, reviews=reviews, season=2025, week=5)
    stats[-1]["fantasy_points_ppr"] = 9999
    after = build(stats=stats, reviews=reviews, season=2025, week=5)
    assert before == after
    assert predict_baseline(
        build(stats=stats, reviews=reviews, season=2025, week=6)
    ) != predict_baseline(before)


def test_future_evidence_cannot_change_forecast():
    reviews = [
        evidence(r["game_id"], status="dnf", published=CUTOFF + timedelta(hours=1))
        for r in history()
    ]
    assert predict_baseline(build(reviews=reviews)) == predict_baseline(build(reviews=[]))


def test_reported_dnf_is_excluded_without_reports_for_other_games():
    assert predict_baseline(build(reviews=[evidence("game5", "dnf")])) == 6


def test_shuffled_history_same_result():
    assert build(stats=list(reversed(history()))) == build()


def test_limited_history_and_no_history():
    assert predict_baseline(build(stats=history()[:2])) == 5
    assert build(stats=history()[:2])["history_quality"] == "limited"
    assert predict_baseline(build(stats=[])) is None


def test_missing_stat_appearance_blocks_average():
    missing = dict(history()[0], game_id="missing")
    features = build(participation=[missing])
    assert features["unavailable_reason"] == "incomplete_stat_coverage"
    assert predict_baseline(features) is None


def test_evidence_requires_timezone_and_valid_chronology():
    original = evidence("game1").model_dump()
    with pytest.raises(ValidationError):
        CompletionEvidence(**{**original, "reviewed_at": datetime(2025, 1, 1)})
    with pytest.raises(ValidationError):
        CompletionEvidence(
            **{**original, "retrieved_at": CUTOFF, "reviewed_at": CUTOFF - timedelta(days=1)}
        )


def test_conflicting_equally_recent_evidence_stays_unknown():
    records = [evidence("game1", "dnf"), evidence("game1", "finished")]
    assert completion_at(records, "player", "game1", CUTOFF) == "unknown"


def test_newer_source_return_report_supersedes_earlier_exit_report():
    records = [evidence("game1", "dnf"), evidence("game1", "finished", CUTOFF - timedelta(days=1))]
    assert completion_at(records, "player", "game1", CUTOFF) == "finished"


def test_unmatched_schedule_does_not_shrink_history_silently():
    rows = history()
    rows[-1]["game_datetime"] = None
    features = build(stats=rows)
    assert features["unavailable_reason"] == "unverified_schedule"
    assert predict_baseline(features) is None
