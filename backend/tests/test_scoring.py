import pytest

from src.domain.scoring import FantasyStats, calculate_full_ppr


def test_zero_stat_line_scores_zero() -> None:
    assert calculate_full_ppr(FantasyStats()) == 0.0


def test_receiving_stat_line_scores_full_ppr() -> None:
    stats = FantasyStats(receptions=5, receiving_yards=60, receiving_tds=1)

    assert calculate_full_ppr(stats) == 17.0


def test_mixed_production_and_turnovers() -> None:
    stats = FantasyStats(
        passing_yards=25,
        passing_tds=1,
        interceptions=1,
        rushing_yards=40,
        rushing_tds=1,
        receptions=4,
        receiving_yards=50,
        receiving_tds=1,
        fumbles_lost_total=1,
    )

    assert calculate_full_ppr(stats) == pytest.approx(26.0)
