"""Thin UI adapter for the existing public SQLite persistence API."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from kz_ecomops.reconciliation import (
    ReconciliationResult,
    ReviewStatus,
)
from kz_ecomops.storage import (
    AnomalyStorageWriteResult,
    StorageWriteResult,
    persist_reconciliation_result,
    persist_validated_dataset,
    read_stored_anomalies,
    update_anomaly_status,
)
from kz_ecomops.validation import DatasetValidationResult


DEFAULT_RUNTIME_DATABASE = Path(".runtime") / "kz-ecomops-control-tower.sqlite3"


@dataclass(frozen=True, slots=True)
class PersistenceOutcome:
    """Return refreshed review states and idempotent persistence counts."""

    reconciliation_result: ReconciliationResult
    dataset_write: StorageWriteResult
    anomaly_write: AnomalyStorageWriteResult


def runtime_database_path() -> Path:
    """Return the documented local path, with a test/runtime override."""

    override = os.environ.get("KZ_ECOMOPS_DB_PATH")
    return Path(override) if override else DEFAULT_RUNTIME_DATABASE


def persist_and_refresh(
    database_path: str | Path,
    validation_result: DatasetValidationResult,
    reconciliation_result: ReconciliationResult,
) -> PersistenceOutcome:
    """Persist through public APIs and reload preserved review states."""

    dataset_write = persist_validated_dataset(database_path, validation_result)
    anomaly_write = persist_reconciliation_result(
        database_path,
        reconciliation_result,
    )
    stored_by_id = {
        stored.anomaly.anomaly_id: stored.anomaly
        for stored in read_stored_anomalies(database_path)
    }
    refreshed = replace(
        reconciliation_result,
        anomalies=tuple(
            stored_by_id.get(anomaly.anomaly_id, anomaly)
            for anomaly in reconciliation_result.anomalies
        ),
    )
    return PersistenceOutcome(refreshed, dataset_write, anomaly_write)


def change_review_status(
    database_path: str | Path,
    reconciliation_result: ReconciliationResult,
    anomaly_id: str,
    review_status: ReviewStatus | str,
) -> ReconciliationResult:
    """Update one stored status and return a new immutable result for the UI."""

    stored = update_anomaly_status(database_path, anomaly_id, review_status)
    return replace(
        reconciliation_result,
        anomalies=tuple(
            stored.anomaly if anomaly.anomaly_id == anomaly_id else anomaly
            for anomaly in reconciliation_result.anomalies
        ),
    )
