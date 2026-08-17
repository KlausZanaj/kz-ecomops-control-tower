"""Full synthetic export-to-SQLite integration tests."""

from __future__ import annotations

from pathlib import Path

from kz_ecomops.normalization import normalize_all_platforms, write_canonical_csvs
from kz_ecomops.storage import count_stored_records, persist_validated_dataset
from kz_ecomops.validation import CSV_SCHEMAS, validate_dataset_directory


PROJECT_ROOT = Path(__file__).parents[2]
SOURCE_ROOT = PROJECT_ROOT / "data" / "sample" / "sources"


def test_four_platform_exports_reach_idempotent_sqlite_storage(
    tmp_path: Path,
) -> None:
    source_paths = tuple(SOURCE_ROOT.rglob("*.csv"))
    source_before = {path: path.read_bytes() for path in source_paths}

    normalized = normalize_all_platforms(SOURCE_ROOT)
    assert normalized.is_valid
    assert normalized.dataframes is not None
    assert all(len(dataframe) == 4 for dataframe in normalized.dataframes.values())

    canonical_directory = tmp_path / "canonical"
    canonical_paths = write_canonical_csvs(normalized, canonical_directory)
    canonical_before = {path: path.read_bytes() for path in canonical_paths}
    validated = validate_dataset_directory(canonical_directory)

    assert validated.report.reconciliation_ready
    assert validated.report.blocking_message_count == 0
    assert validated.report.relationship_finding_count == 0
    assert validated.report.rejected_row_count == 0
    assert validated.dataframes is not None

    database = tmp_path / "pipeline.sqlite3"
    first = persist_validated_dataset(database, validated)
    second = persist_validated_dataset(database, validated)

    expected_counts = {filename: 4 for filename in CSV_SCHEMAS}
    assert first.inserted_counts == expected_counts
    assert first.existing_total == 0
    assert second.inserted_total == 0
    assert second.existing_counts == expected_counts
    assert count_stored_records(database) == expected_counts
    assert {path: path.read_bytes() for path in source_paths} == source_before
    assert {path: path.read_bytes() for path in canonical_paths} == canonical_before
