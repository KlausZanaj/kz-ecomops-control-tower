"""Integration coverage from canonical samples through anomaly persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from kz_ecomops.reconciliation import reconcile_dataset
from kz_ecomops.storage import (
    count_stored_records,
    persist_reconciliation_result,
    persist_validated_dataset,
    read_stored_anomalies,
)
from kz_ecomops.validation import validate_dataset_directory


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = PROJECT_ROOT / "data" / "sample"


def test_validation_reconciliation_and_storage_pipeline(tmp_path: Path) -> None:
    validation = validate_dataset_directory(
        SAMPLE_ROOT / "scenarios" / "rec-05-shipment-without-tracking"
    )
    result = reconcile_dataset(
        validation,
        datetime(2026, 3, 20, 12, tzinfo=timezone.utc),
    )
    database = tmp_path / "control-tower.db"

    canonical_write = persist_validated_dataset(database, validation)
    anomaly_write = persist_reconciliation_result(database, result)

    assert canonical_write.inserted_total == 3
    assert count_stored_records(database)["shipments.csv"] == 1
    assert anomaly_write.inserted_count == 1
    assert read_stored_anomalies(database)[0].anomaly == result.anomalies[0]
