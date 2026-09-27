"""The baseline never substitutes a guessed score for unavailable history."""

from typing import Any

BASELINE_VERSION = "trailing_four_v2_reported_dnf_excluded"


def predict_baseline(features: dict[str, Any]) -> float | None:
    if features["unavailable_reason"] is not None:
        return None
    return features["ppr_points_avg_4"]
