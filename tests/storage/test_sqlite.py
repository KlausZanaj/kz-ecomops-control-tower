"""Tests for transactional idempotent SQLite persistence."""

from __future__ import annotations

import sqlite3
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType

import pandas as pd
import pytest

from kz_ecomops.storage import (
    STORAGE_TABLES,
    DatasetStorageError,
    StorageErrorCode,
    count_stored_records,
    initialize_database,
    persist_validated_dataset,
    read_stored_records,
)
from kz_ecomops.validation import CSV_SCHEMAS, DatasetValidationResult, validate_dataset_directory


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = PROJECT_ROOT / "data" / "sample"


def _validated(directory: Path | None = None) -> DatasetValidationResult:
    result = validate_dataset_directory(directory or SAMPLE_ROOT / "normalized" / "valid")
    assert result.report.reconciliation_ready
    assert result.dataframes is not None
    return result


def _scenario(prefix: str) -> Path:
    return next((SAMPLE_ROOT / "scenarios").glob(f"{prefix}-*"))


def _write_flexible_dataset(
    directory: Path,
    *,
    omit_optional: bool = False,
    extra_value: str | None = None,
    reverse_columns: bool = False,
) -> DatasetValidationResult:
    source = _validated()
    assert source.dataframes is not None
    directory.mkdir()
    conditionally_required = {
        "payments.csv": {"paid_at"},
        "shipments.csv": {"shipped_at", "delivered_at"},
        "returns.csv": {"received_at", "expected_refund_amount", "currency"},
        "refunds.csv": {"refunded_at"},
    }
    for filename, dataframe in source.dataframes.items():
        flexible = dataframe.copy(deep=True)
        if omit_optional:
            removable = [
                column.name
                for column in CSV_SCHEMAS[filename].columns
                if not column.required
                and column.name not in conditionally_required.get(filename, set())
            ]
            flexible = flexible.drop(columns=removable)
        if extra_value is not None:
            flexible["ignored_source_context"] = extra_value
        if reverse_columns:
            flexible = flexible.loc[:, tuple(reversed(flexible.columns))]
        flexible.to_csv(directory / filename, index=False, lineterminator="\n")
    result = validate_dataset_directory(directory)
    assert result.report.reconciliation_ready
    assert result.dataframes is not None
    return result


def test_initializes_five_tables_without_cross_file_foreign_keys(tmp_path: Path) -> None:
    database = tmp_path / "control-tower.sqlite"

    result = initialize_database(database)

    assert result.database_path == database
    assert result.tables == tuple(STORAGE_TABLES.values())
    with sqlite3.connect(database) as connection:
        definitions = dict(
            connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type = ?",
                ("table",),
            ).fetchall()
        )
    assert set(definitions) == set(STORAGE_TABLES.values())
    assert all("FOREIGN KEY" not in statement.upper() for statement in definitions.values())


@pytest.mark.parametrize("filename", tuple(CSV_SCHEMAS))
def test_table_columns_preserve_canonical_order(filename: str, tmp_path: Path) -> None:
    database = tmp_path / "schema.db"
    initialize_database(database)

    with sqlite3.connect(database) as connection:
        columns = tuple(
            row[1]
            for row in connection.execute(
                f'PRAGMA table_info("{STORAGE_TABLES[filename]}")'
            )
        )

    assert columns == ("_record_key", "_source_row_number", *CSV_SCHEMAS[filename].column_names)


def test_persists_valid_dataset_and_reports_counts(tmp_path: Path) -> None:
    database = tmp_path / "valid.sqlite3"

    write = persist_validated_dataset(database, _validated())

    assert write.inserted_counts == {filename: 4 for filename in CSV_SCHEMAS}
    assert write.existing_counts == {filename: 0 for filename in CSV_SCHEMAS}
    assert write.inserted_total == 20
    assert write.existing_total == 0
    assert count_stored_records(database) == {filename: 4 for filename in CSV_SCHEMAS}


def test_reads_traceability_amounts_and_timezone_dates_as_text(tmp_path: Path) -> None:
    database = tmp_path / "values.db"
    persist_validated_dataset(database, _validated())

    payments = read_stored_records(database, "payments.csv")

    assert payments[0].source_row_number == 1
    assert len(payments[0].record_key) == 64
    assert payments[0].values["amount"] == "100.00"
    assert payments[0].values["paid_at"].endswith("+00:00")
    with sqlite3.connect(database) as connection:
        sqlite_type = connection.execute(
            'SELECT typeof("amount") FROM "payments" LIMIT 1'
        ).fetchone()[0]
    assert sqlite_type == "text"


def test_second_import_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "idempotent.sqlite"
    result = _validated()

    first = persist_validated_dataset(database, result)
    second = persist_validated_dataset(database, result)

    assert first.inserted_total == 20
    assert second.inserted_total == 0
    assert second.existing_counts == {filename: 4 for filename in CSV_SCHEMAS}
    assert count_stored_records(database) == {filename: 4 for filename in CSV_SCHEMAS}


def test_persists_validated_dataframes_with_optional_columns_absent(
    tmp_path: Path,
) -> None:
    result = _write_flexible_dataset(
        tmp_path / "optional-columns-absent",
        omit_optional=True,
    )
    assert result.dataframes is not None
    originals = {
        filename: dataframe.copy(deep=True)
        for filename, dataframe in result.dataframes.items()
    }
    database = tmp_path / "optional-columns.db"

    first = persist_validated_dataset(database, result)
    second = persist_validated_dataset(database, result)

    assert first.inserted_counts == {filename: 4 for filename in CSV_SCHEMAS}
    assert second.inserted_total == 0
    assert second.existing_counts == {filename: 4 for filename in CSV_SCHEMAS}
    assert read_stored_records(database, "orders.csv")[0].values["order_number"] == ""
    assert read_stored_records(database, "payments.csv")[0].values["payment_method"] == ""
    assert read_stored_records(database, "shipments.csv")[0].values["carrier"] == ""
    assert read_stored_records(database, "returns.csv")[0].values["return_reason"] == ""
    assert read_stored_records(database, "refunds.csv")[0].values["reason"] == ""
    for filename in CSV_SCHEMAS:
        pd.testing.assert_frame_equal(result.dataframes[filename], originals[filename])


def test_ignores_extra_columns_and_extra_value_changes_for_idempotency(
    tmp_path: Path,
) -> None:
    first_result = _write_flexible_dataset(
        tmp_path / "extra-columns-first",
        extra_value="first-synthetic-context",
    )
    second_result = _write_flexible_dataset(
        tmp_path / "extra-columns-second",
        extra_value="changed-synthetic-context",
    )
    assert first_result.dataframes is not None
    assert second_result.dataframes is not None
    assert "ignored_source_context" in first_result.dataframes["orders.csv"].columns
    original = first_result.dataframes["orders.csv"].copy(deep=True)
    database = tmp_path / "extra-columns.db"

    first = persist_validated_dataset(database, first_result)
    second = persist_validated_dataset(database, second_result)

    assert first.inserted_total == 20
    assert second.inserted_total == 0
    assert second.existing_total == 20
    assert "ignored_source_context" in first_result.dataframes["orders.csv"].columns
    pd.testing.assert_frame_equal(first_result.dataframes["orders.csv"], original)
    with sqlite3.connect(database) as connection:
        table_columns = {
            row[1] for row in connection.execute('PRAGMA table_info("orders")')
        }
    assert "ignored_source_context" not in table_columns


def test_persists_reordered_columns_in_canonical_storage_positions(
    tmp_path: Path,
) -> None:
    result = _write_flexible_dataset(
        tmp_path / "reordered-columns",
        reverse_columns=True,
    )
    assert result.dataframes is not None
    assert tuple(result.dataframes["orders.csv"].columns) == tuple(
        reversed(CSV_SCHEMAS["orders.csv"].column_names)
    )
    original = result.dataframes["payments.csv"].copy(deep=True)
    database = tmp_path / "reordered-columns.db"

    first = persist_validated_dataset(database, result)
    second = persist_validated_dataset(database, result)
    stored_order = read_stored_records(database, "orders.csv")[0]
    stored_payment = read_stored_records(database, "payments.csv")[0]

    assert first.inserted_total == 20
    assert second.inserted_total == 0
    assert second.existing_total == 20
    assert stored_order.values["order_id"] == "shopify:SYN-SH-1001"
    assert stored_order.values["source_order_id"] == "SYN-SH-1001"
    assert stored_payment.values["amount"] == "100.00"
    assert stored_payment.values["currency"] == "EUR"
    pd.testing.assert_frame_equal(result.dataframes["payments.csv"], original)


def test_deterministic_keys_match_across_fresh_databases(tmp_path: Path) -> None:
    first_database = tmp_path / "first.db"
    second_database = tmp_path / "second.db"
    result = _validated()
    persist_validated_dataset(first_database, result)
    persist_validated_dataset(second_database, result)

    for filename in CSV_SCHEMAS:
        assert [record.record_key for record in read_stored_records(first_database, filename)] == [
            record.record_key for record in read_stored_records(second_database, filename)
        ]


def test_preserves_rec10_orphan_records(tmp_path: Path) -> None:
    result = _validated(_scenario("rec-10"))
    assert result.report.relationship_finding_count == 1
    database = tmp_path / "orphan.db"

    persist_validated_dataset(database, result)
    shipments = read_stored_records(database, "shipments.csv")

    assert len(shipments) == 2
    assert any(record.values["order_id"] == "shopify:REC10-MISSING-9001" for record in shipments)


@pytest.mark.parametrize(
    ("scenario_prefix", "filename", "identifier"),
    [
        ("rec-04", "payments.csv", "payment_id"),
        ("rec-09", "refunds.csv", "refund_id"),
    ],
)
def test_preserves_exact_duplicates_once_per_occurrence(
    scenario_prefix: str,
    filename: str,
    identifier: str,
    tmp_path: Path,
) -> None:
    result = _validated(_scenario(scenario_prefix))
    database = tmp_path / f"{scenario_prefix}.db"

    first = persist_validated_dataset(database, result)
    second = persist_validated_dataset(database, result)
    records = read_stored_records(database, filename)

    assert first.inserted_counts[filename] == 2
    assert second.existing_counts[filename] == 2
    assert len(records) == 2
    assert records[0].values[identifier] == records[1].values[identifier]
    assert records[0].record_key != records[1].record_key


def test_transaction_rolls_back_all_tables_on_database_error(tmp_path: Path) -> None:
    database = tmp_path / "rollback.db"
    initialize_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_shipments
            BEFORE INSERT ON shipments
            BEGIN
                SELECT RAISE(ABORT, 'synthetic rollback test');
            END
            """
        )

    with pytest.raises(DatasetStorageError) as captured:
        persist_validated_dataset(database, _validated())

    assert captured.value.code is StorageErrorCode.DATABASE_ERROR
    assert count_stored_records(database) == {filename: 0 for filename in CSV_SCHEMAS}


def test_rejects_blocking_result_before_creating_database(tmp_path: Path) -> None:
    invalid = validate_dataset_directory(SAMPLE_ROOT / "invalid" / "missing-paid-at")
    database = tmp_path / "must-not-exist.db"

    with pytest.raises(DatasetStorageError) as captured:
        persist_validated_dataset(database, invalid)

    assert captured.value.code is StorageErrorCode.NOT_RECONCILIATION_READY
    assert not database.exists()


def test_rejects_incomplete_dataframe_mapping(tmp_path: Path) -> None:
    valid = _validated()
    assert valid.dataframes is not None
    incomplete = DatasetValidationResult(
        report=valid.report,
        dataframes={
            filename: dataframe
            for filename, dataframe in valid.dataframes.items()
            if filename != "refunds.csv"
        },
    )
    database = tmp_path / "incomplete.db"

    with pytest.raises(DatasetStorageError) as captured:
        persist_validated_dataset(database, incomplete)

    assert captured.value.code is StorageErrorCode.INCOMPLETE_DATASET
    assert not database.exists()


def test_rejects_artificial_result_missing_required_column_before_database_creation(
    tmp_path: Path,
) -> None:
    valid = _validated()
    assert valid.dataframes is not None
    artificial = DatasetValidationResult(
        report=valid.report,
        dataframes={
            filename: (
                dataframe.drop(columns=["currency"])
                if filename == "orders.csv"
                else dataframe
            )
            for filename, dataframe in valid.dataframes.items()
        },
    )
    database = tmp_path / "missing-required.db"

    with pytest.raises(DatasetStorageError) as captured:
        persist_validated_dataset(database, artificial)

    assert captured.value.code is StorageErrorCode.INCOMPLETE_DATASET
    assert not database.exists()


def test_rejects_non_result_object(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="DatasetValidationResult"):
        persist_validated_dataset(tmp_path / "invalid.db", {})  # type: ignore[arg-type]


def test_conflicting_unique_record_rolls_back_new_dataset(tmp_path: Path) -> None:
    database = tmp_path / "conflict.db"
    original = _validated()
    persist_validated_dataset(database, original)
    before = dict(count_stored_records(database))

    changed_directory = tmp_path / "changed"
    changed_directory.mkdir()
    for filename, dataframe in original.dataframes.items():  # type: ignore[union-attr]
        changed = dataframe.copy(deep=True)
        if filename == "orders.csv":
            changed.loc[0, "order_number"] = "DEMO-CHANGED"
        changed.to_csv(changed_directory / filename, index=False, lineterminator="\n")
    changed_result = _validated(changed_directory)

    with pytest.raises(DatasetStorageError) as captured:
        persist_validated_dataset(database, changed_result)

    assert captured.value.code is StorageErrorCode.CONFLICTING_RECORD
    assert dict(count_stored_records(database)) == before


def test_persistence_does_not_modify_dataframes_and_reads_do_not_modify_database(
    tmp_path: Path,
) -> None:
    result = _validated()
    assert result.dataframes is not None
    originals = {
        filename: dataframe.copy(deep=True)
        for filename, dataframe in result.dataframes.items()
    }
    database = tmp_path / "unchanged.db"

    persist_validated_dataset(database, result)
    for filename in CSV_SCHEMAS:
        pd.testing.assert_frame_equal(result.dataframes[filename], originals[filename])
    before = database.read_bytes()
    count_stored_records(database)
    for filename in CSV_SCHEMAS:
        read_stored_records(database, filename)
    assert database.read_bytes() == before


def test_public_results_are_frozen_slotted_and_protected(tmp_path: Path) -> None:
    write = persist_validated_dataset(tmp_path / "protected.db", _validated())
    record = read_stored_records(tmp_path / "protected.db", "orders.csv")[0]

    assert isinstance(write.inserted_counts, MappingProxyType)
    assert isinstance(record.values, MappingProxyType)
    with pytest.raises(FrozenInstanceError):
        write.inserted_counts = {}  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        record.source_row_number = 2  # type: ignore[misc]
    assert not hasattr(write, "__dict__")
    assert not hasattr(record, "__dict__")


def test_storage_error_codes_are_exact() -> None:
    assert {code.value for code in StorageErrorCode} == {
        "invalid_result",
        "incomplete_dataset",
        "not_reconciliation_ready",
        "conflicting_record",
        "database_error",
    }
