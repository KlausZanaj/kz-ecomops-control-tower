"""SQLite persistence tests for deterministic reconciliation anomalies."""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from kz_ecomops.reconciliation import (
    ReconciliationResult,
    ReviewStatus,
    Severity,
    reconcile_dataset,
)
from kz_ecomops.storage import (
    ANOMALY_TABLE,
    DatasetStorageError,
    StorageErrorCode,
    count_stored_records,
    persist_reconciliation_result,
    persist_validated_dataset,
    read_stored_anomalies,
    update_anomaly_status,
)
from kz_ecomops.validation import CSV_SCHEMAS, validate_dataset_directory


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = PROJECT_ROOT / "data" / "sample"
REFERENCE_AT = datetime(2026, 3, 20, 12, tzinfo=timezone.utc)


def _validation(scenario: str = "rec-01-payment-amount-mismatch"):
    return validate_dataset_directory(SAMPLE_ROOT / "scenarios" / scenario)


def _result(scenario: str = "rec-01-payment-amount-mismatch", reference_at: datetime = REFERENCE_AT):
    return reconcile_dataset(_validation(scenario), reference_at)


def _collision_result(
    directory: Path,
    *,
    reverse: bool = False,
) -> ReconciliationResult:
    directory.mkdir()
    payments = [
        {
            "payment_id": "DUP-PAY",
            "platform": "shopify",
            "order_id": f"shopify:MISSING-{suffix}",
            "source_order_id": f"MISSING-{suffix}",
            "provider_transaction_id": "TXN-X",
            "payment_method": "synthetic_card",
            "payment_status": "succeeded",
            "amount": "10.00",
            "currency": "EUR",
            "paid_at": "2026-03-01T10:00:00+00:00",
            "created_at": "2026-03-01T09:59:00+00:00",
            "updated_at": "2026-03-01T10:00:00+00:00",
        }
        for suffix in ("A", "B")
    ]
    if reverse:
        payments.reverse()
    rows = {filename: [] for filename in CSV_SCHEMAS}
    rows["payments.csv"] = payments
    for filename, schema in CSV_SCHEMAS.items():
        pd.DataFrame(
            rows[filename],
            columns=schema.column_names,
            dtype=str,
        ).to_csv(directory / filename, index=False)
    validation = validate_dataset_directory(directory)
    assert validation.report.reconciliation_ready
    return reconcile_dataset(validation, REFERENCE_AT)


def test_persists_and_reads_deterministic_anomaly_json(tmp_path: Path) -> None:
    database = tmp_path / "anomalies.db"
    result = _result()

    write = persist_reconciliation_result(database, result)
    stored = read_stored_anomalies(database)

    assert write.inserted_count == 1
    assert write.existing_count == 0
    assert len(stored) == 1
    assert stored[0].anomaly == result.anomalies[0]
    assert stored[0].first_detected_at == REFERENCE_AT
    assert stored[0].last_detected_at == REFERENCE_AT
    with sqlite3.connect(database) as connection:
        compared_json, references_json = connection.execute(
            f'SELECT "compared_values_json", "record_references_json" FROM "{ANOMALY_TABLE}"'
        ).fetchone()
    assert compared_json == json.dumps(
        dict(result.anomalies[0].compared_values),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert json.loads(references_json)[0] == {
        "filename": result.anomalies[0].record_references[0].filename,
        "record_id": result.anomalies[0].record_references[0].record_id,
        "row_number": result.anomalies[0].record_references[0].row_number,
    }


def test_second_persistence_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "idempotent.db"
    result = _result()

    first = persist_reconciliation_result(database, result)
    second = persist_reconciliation_result(database, result)

    assert first.inserted_count == 1 and first.existing_count == 0
    assert second.inserted_count == 0 and second.existing_count == 1
    assert len(read_stored_anomalies(database)) == 1


def test_reordered_records_keep_ids_and_refresh_stored_row_references(
    tmp_path: Path,
) -> None:
    source = SAMPLE_ROOT / "scenarios" / "rec-10-cross-system-record-missing"
    reordered_directory = tmp_path / "reordered"
    shutil.copytree(source, reordered_directory)
    shipments_path = reordered_directory / "shipments.csv"
    shipments = pd.read_csv(shipments_path, dtype=str, keep_default_na=False)
    shipments.iloc[::-1].reset_index(drop=True).to_csv(shipments_path, index=False)

    original_result = reconcile_dataset(
        validate_dataset_directory(source),
        REFERENCE_AT,
    )
    reordered_result = reconcile_dataset(
        validate_dataset_directory(reordered_directory),
        REFERENCE_AT,
    )

    assert {item.anomaly_id for item in original_result.anomalies} == {
        item.anomaly_id for item in reordered_result.anomalies
    }
    original_reference = next(
        reference
        for reference in original_result.anomalies[0].record_references
        if reference.record_id == "ship-REC10-MISSING-9001"
    )
    reordered_reference = next(
        reference
        for reference in reordered_result.anomalies[0].record_references
        if reference.record_id == "ship-REC10-MISSING-9001"
    )
    assert original_reference.row_number == 2
    assert reordered_reference.row_number == 1

    database = tmp_path / "reordered.db"
    first = persist_reconciliation_result(database, original_result)
    second = persist_reconciliation_result(database, reordered_result)
    stored_reference = next(
        reference
        for reference in read_stored_anomalies(database)[0].anomaly.record_references
        if reference.record_id == "ship-REC10-MISSING-9001"
    )

    assert first.inserted_count == 1 and first.existing_count == 0
    assert second.inserted_count == 0 and second.existing_count == 1
    assert stored_reference.row_number == 1


def test_semantic_rec10_ids_are_idempotent_after_payment_reordering(
    tmp_path: Path,
) -> None:
    original = _collision_result(tmp_path / "collision-original")
    reordered = _collision_result(tmp_path / "collision-reordered", reverse=True)
    database = tmp_path / "semantic-collision.db"

    first = persist_reconciliation_result(database, original)
    second = persist_reconciliation_result(database, reordered)
    stored = read_stored_anomalies(database)
    stored_rec10 = {
        item.anomaly.order_id: item.anomaly
        for item in stored
        if item.anomaly.rule_code.value == "REC-10"
    }

    assert {item.anomaly_id for item in original.anomalies} == {
        item.anomaly_id for item in reordered.anomalies
    }
    assert first.inserted_count == 3 and first.existing_count == 0
    assert second.inserted_count == 0 and second.existing_count == 3
    assert len(stored) == 3
    assert set(stored_rec10) == {"shopify:MISSING-A", "shopify:MISSING-B"}
    assert {
        order_id: anomaly.record_references[0].row_number
        for order_id, anomaly in stored_rec10.items()
    } == {"shopify:MISSING-A": 2, "shopify:MISSING-B": 1}


def test_review_status_and_first_detection_survive_later_upsert(tmp_path: Path) -> None:
    database = tmp_path / "review.db"
    first_result = _result()
    persist_reconciliation_result(database, first_result)
    anomaly_id = first_result.anomalies[0].anomaly_id

    updated = update_anomaly_status(database, anomaly_id, ReviewStatus.IN_REVIEW)
    assert updated.anomaly.review_status is ReviewStatus.IN_REVIEW

    later_at = REFERENCE_AT + timedelta(days=1)
    later_result = _result(reference_at=later_at)
    changed_anomaly = replace(
        later_result.anomalies[0],
        severity=Severity.CRITICAL,
        description="Updated deterministic explanation.",
    )
    changed_result = ReconciliationResult(
        reference_at=later_at,
        config=later_result.config,
        anomalies=(changed_anomaly,),
    )
    persist_reconciliation_result(database, changed_result)
    stored = read_stored_anomalies(database)[0]

    assert stored.anomaly.review_status is ReviewStatus.IN_REVIEW
    assert stored.anomaly.severity is Severity.CRITICAL
    assert stored.anomaly.description == "Updated deterministic explanation."
    assert stored.first_detected_at == REFERENCE_AT
    assert stored.last_detected_at == later_at


def test_invalid_and_missing_review_status_updates_are_explicit(tmp_path: Path) -> None:
    database = tmp_path / "status.db"
    persist_reconciliation_result(database, _result())
    with pytest.raises(ValueError, match="not a supported"):
        update_anomaly_status(database, "missing", "invalid")
    with pytest.raises(KeyError, match="No stored anomaly"):
        update_anomaly_status(database, "missing", ReviewStatus.RESOLVED)


def test_phase4_database_is_extended_without_losing_canonical_records(tmp_path: Path) -> None:
    database = tmp_path / "phase4.db"
    validation = validate_dataset_directory(SAMPLE_ROOT / "normalized" / "valid")
    persist_validated_dataset(database, validation)
    before = dict(count_stored_records(database))

    persist_reconciliation_result(database, _result())

    assert dict(count_stored_records(database)) == before
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert ANOMALY_TABLE in tables


def test_anomaly_transaction_rolls_back_all_inserts(tmp_path: Path) -> None:
    database = tmp_path / "rollback.db"
    first = _result("rec-01-payment-amount-mismatch")
    second = _result("rec-02-paid-not-shipped-on-time", datetime(2026, 3, 4, 12, tzinfo=timezone.utc))
    combined = ReconciliationResult(
        reference_at=REFERENCE_AT,
        config=first.config,
        anomalies=(first.anomalies[0], second.anomalies[0]),
    )
    persist_reconciliation_result(
        database,
        ReconciliationResult(REFERENCE_AT, first.config),
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            f"""
            CREATE TRIGGER fail_rec02 BEFORE INSERT ON "{ANOMALY_TABLE}"
            WHEN NEW.rule_code = 'REC-02'
            BEGIN SELECT RAISE(ABORT, 'forced failure'); END
            """
        )

    with pytest.raises(DatasetStorageError) as captured:
        persist_reconciliation_result(database, combined)

    assert captured.value.code is StorageErrorCode.DATABASE_ERROR
    assert read_stored_anomalies(database) == ()
