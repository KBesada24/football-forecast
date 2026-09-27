from pathlib import Path
from typing import Any

import polars as pl
import yaml


class SourceSchemaError(ValueError):
    """Raised when runtime source data does not match the verified mapping."""


def load_schema_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as mapping_file:
        mapping = yaml.safe_load(mapping_file)

    if not isinstance(mapping, dict) or "datasets" not in mapping:
        raise SourceSchemaError(f"Invalid source schema mapping: {path}")
    return mapping


def validate_source_schema(
    frame: pl.DataFrame,
    mapping: dict[str, Any],
    dataset_name: str,
) -> None:
    try:
        fields = mapping["datasets"][dataset_name]["fields"]
    except KeyError as error:
        raise SourceSchemaError(f"Mapping does not define dataset {dataset_name!r}") from error

    missing_fields: list[str] = []
    wrong_dtypes: list[str] = []

    for canonical_name, field_config in fields.items():
        raw_name = field_config.get("chosen_raw_field")
        if raw_name is None:
            continue
        if raw_name not in frame.columns:
            if field_config.get("required", False):
                missing_fields.append(f"{canonical_name} <- {raw_name}")
            continue

        expected_dtype = field_config.get("raw_dtype")
        actual_dtype = str(frame.schema[raw_name])
        if expected_dtype and actual_dtype != expected_dtype:
            wrong_dtypes.append(
                f"{canonical_name} <- {raw_name}: expected {expected_dtype}, got {actual_dtype}"
            )

    errors: list[str] = []
    if missing_fields:
        errors.append("missing required fields: " + ", ".join(missing_fields))
    if wrong_dtypes:
        errors.append("unexpected dtypes: " + "; ".join(wrong_dtypes))
    if errors:
        raise SourceSchemaError(f"{dataset_name} schema validation failed: {'; '.join(errors)}")
