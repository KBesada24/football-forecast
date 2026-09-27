import polars as pl

from src.jobs.audit_nflreadpy_schema import summarize_frame


def test_summarize_frame_records_schema_nulls_and_samples() -> None:
    frame = pl.DataFrame(
        {
            "player_id": ["p1", "p2"],
            "targets": [3, None],
        }
    )

    summary = summarize_frame(frame)

    assert summary["row_count"] == 2
    assert summary["column_count"] == 2
    assert summary["schema"] == {"player_id": "String", "targets": "Int64"}
    assert summary["null_counts"] == {"player_id": 0, "targets": 1}
    assert summary["sample_records"][0] == {"player_id": "p1", "targets": 3}
