"""Tests for idempotent UI persistence and immutable review-state changes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from kz_ecomops.reconciliation import ReviewStatus, reconcile_dataset
from kz_ecomops.storage import read_stored_anomalies
from kz_ecomops.ui import change_review_status, persist_and_refresh
from kz_ecomops.validation import validate_dataset_directory


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = PROJECT_ROOT / "data" / "sample"
REFERENCE_AT = datetime(2026, 3, 20, 12, tzinfo=timezone.utc)


def test_review_status_survives_reconciliation_repersistence_without_mutation(
    tmp_path: Path,
) -> None:
    validation = validate_dataset_directory(
        SAMPLE_ROOT / "scenarios" / "rec-01-payment-amount-mismatch"
    )
    result = reconcile_dataset(validation, REFERENCE_AT)
    assert validation.dataframes is not None
    frame_copies = {
        filename: dataframe.copy(deep=True)
        for filename, dataframe in validation.dataframes.items()
    }
    original_anomaly = result.anomalies[0]
    database = tmp_path / "ui.db"

    first = persist_and_refresh(database, validation, result)
    updated = change_review_status(
        database,
        first.reconciliation_result,
        original_anomaly.anomaly_id,
        ReviewStatus.RESOLVED,
    )
    second = persist_and_refresh(database, validation, result)
    stored = read_stored_anomalies(database)

    assert first.anomaly_write.inserted_count == 1
    assert second.anomaly_write.inserted_count == 0
    assert second.anomaly_write.existing_count == 1
    assert len(stored) == 1
    assert updated.anomalies[0].review_status is ReviewStatus.RESOLVED
    assert second.reconciliation_result.anomalies[0].review_status is ReviewStatus.RESOLVED
    assert result.anomalies[0] == original_anomaly
    assert result.anomalies[0].review_status is ReviewStatus.OPEN
    for filename, dataframe in validation.dataframes.items():
        pd.testing.assert_frame_equal(dataframe, frame_copies[filename])


def test_status_update_changes_only_review_state(tmp_path: Path) -> None:
    validation = validate_dataset_directory(
        SAMPLE_ROOT / "scenarios" / "rec-05-shipment-without-tracking"
    )
    result = reconcile_dataset(validation, REFERENCE_AT)
    database = tmp_path / "review.db"
    persisted = persist_and_refresh(database, validation, result)
    before = persisted.reconciliation_result.anomalies[0]

    changed = change_review_status(
        database,
        persisted.reconciliation_result,
        before.anomaly_id,
        "in_review",
    ).anomalies[0]

    assert changed.review_status is ReviewStatus.IN_REVIEW
    assert changed.anomaly_id == before.anomaly_id
    assert changed.severity == before.severity
    assert changed.description == before.description
    assert changed.compared_values == before.compared_values
    assert changed.record_references == before.record_references
