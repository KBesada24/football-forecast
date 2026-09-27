"""Small transparent ridge challenger, trained offline with chronological evaluation.

No third-party ML runtime is needed to evaluate nine frozen coefficients. Validation
chooses the challenger; a single untouched holdout gates deployment against both
five-game baselines. Failed positions keep the simple baseline, with results recorded.
"""

from collections import defaultdict
from itertools import combinations
from math import sqrt
from statistics import mean

from src.domain.espn import POSITIONS, SCORING_VERSION
from src.features.lineup_features import FEATURE_VERSION, FeatureIndex

MODEL_VERSION = "lineup_ridge_v1"


def fit(samples: list[dict], penalty: float) -> dict:
    vectors = [s["features"]["vector"] for s in samples]
    size = len(vectors[0])
    center = [mean(v[i] for v in vectors) for i in range(size)]
    scale = [sqrt(mean((v[i] - center[i]) ** 2 for v in vectors)) or 1 for i in range(size)]
    xs = [[1.0] + [(v[i] - center[i]) / scale[i] for i in range(size)] for v in vectors]
    ys = [s["actual"] - s["features"]["average5"] for s in samples]
    n = size + 1
    matrix = [
        [sum(x[i] * x[j] for x in xs) + (penalty if i == j and i else 0) for j in range(n)]
        + [sum(x[i] * y for x, y in zip(xs, ys, strict=True))]
        for i in range(n)
    ]
    for i in range(n):
        pivot = max(range(i, n), key=lambda j: abs(matrix[j][i]))
        matrix[i], matrix[pivot] = matrix[pivot], matrix[i]
        divisor = matrix[i][i]
        if abs(divisor) < 1e-12:
            raise ValueError("Singular ridge system")
        matrix[i] = [v / divisor for v in matrix[i]]
        for j in range(n):
            if j != i:
                factor = matrix[j][i]
                matrix[j] = [a - factor * b for a, b in zip(matrix[j], matrix[i], strict=True)]
    return {
        "kind": "ridge",
        "penalty": penalty,
        "center": center,
        "scale": scale,
        "coefficients": [row[-1] for row in matrix],
    }


def predict(model: dict, features: dict) -> float | None:
    if features["unavailable_reason"]:
        return None
    if model["kind"] == "mean5":
        return features["average5"]
    if model["kind"] == "weighted5":
        return features["weighted5"]
    values = [1] + [
        (v - c) / s
        for v, c, s in zip(features["vector"], model["center"], model["scale"], strict=True)
    ]
    return features["average5"] + sum(
        v * c for v, c in zip(values, model["coefficients"], strict=True)
    )


def evaluate(model: dict, samples: list[dict]) -> dict:
    weeks = defaultdict(list)
    errors = []
    for s in samples:
        projected = predict(model, s["features"])
        errors.append(abs(projected - s["actual"]))
        weeks[s["season"], s["week"]].append((s, projected))
    regret = []
    correct = []
    for players in weeks.values():
        # A fixed, baseline-based candidate pool prevents model-dependent evaluation sets.
        candidates = sorted(players, key=lambda v: v[0]["features"]["average5"], reverse=True)[:36]
        for (a, ap), (b, bp) in combinations(candidates, 2):
            if ap == bp:
                regret.append(abs(a["actual"] - b["actual"]) / 2)
                correct.append(0.5)
                continue
            chosen, other = (a, b) if ap > bp else (b, a)
            regret.append(max(0, other["actual"] - chosen["actual"]))
            correct.append(float(chosen["actual"] >= other["actual"]))
    return {
        "samples": len(samples),
        "mae": round(mean(errors), 4) if errors else None,
        "pairwise_regret": round(mean(regret), 4) if regret else None,
        "pairwise_accuracy": round(mean(correct), 4) if correct else None,
        "decision_pairs": len(regret),
    }


def train_and_evaluate(inputs: dict, evidence: list) -> dict:
    index = FeatureIndex(inputs["rows"], evidence)
    samples = defaultdict(list)
    for r in inputs["rows"]:
        if r["missing"] or r["season"] not in (2024, 2025):
            continue
        f = index.build(r["id"], r["position"], r["opponent"], r["season"], r["week"], r["kickoff"])
        # Actual target DNFs remain; only prior history is filtered.
        if not f["unavailable_reason"]:
            samples[r["position"]].append(
                {"features": f, "actual": r["points"], "season": r["season"], "week": r["week"]}
            )
    models, report = {}, {}
    for pos in POSITIONS:
        rows = samples[pos]
        training = [s for s in rows if s["season"] == 2024]
        validation = [s for s in rows if s["season"] == 2025 and s["week"] <= 9]
        holdout = [s for s in rows if s["season"] == 2025 and s["week"] > 9]
        if min(len(training), len(validation), len(holdout)) < 50:
            models[pos] = {"kind": "mean5"}
            report[pos] = {"promoted": False, "reason": "Insufficient chronological samples"}
            continue
        baselines = [{"kind": "mean5"}, {"kind": "weighted5"}]
        baseline = min(baselines, key=lambda m: evaluate(m, validation)["mae"])
        challengers = [fit(training, p) for p in (10, 100, 1000)]
        chosen = min(challengers, key=lambda m: evaluate(m, validation)["mae"])
        frozen = fit(training + validation, chosen["penalty"])
        test = evaluate(frozen, holdout)
        comparisons = {b["kind"]: evaluate(b, holdout) for b in baselines}
        promoted = all(
            test["mae"] < c["mae"] and test["pairwise_regret"] <= c["pairwise_regret"]
            for c in comparisons.values()
        )
        # Do not refit after seeing the holdout. Deployed coefficients remain precisely
        # those tested; 2026 refreshes only change features, never the model.
        models[pos] = frozen if promoted else baseline
        report[pos] = {
            "training": len(training),
            "validation": len(validation),
            "validation_challenger": evaluate(chosen, validation),
            "holdout_challenger": test,
            "holdout_baselines": comparisons,
            "promoted": promoted,
            "deployed": models[pos]["kind"],
        }
    return {
        "version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "scoring_version": SCORING_VERSION,
        "training_artifact": inputs["artifact"],
        "models": models,
        "report": report,
        "evaluation_note": "Corrected-data chronological simulation, "
        "not archived pregame forecasts. "
        "Train: 2024. Tune: 2025 weeks 1–9. Untouched test: 2025 weeks 10–18. "
        "No 2026 outcomes used to train or select models. Pairwise regret is a start/sit proxy, "
        "not a backtest of actual fantasy rosters. Coverage excludes missing recent scoring data.",
    }
