"""Public API for local idempotent SQLite persistence."""

from .sqlite import (
    ANOMALY_TABLE,
    STORAGE_TABLES,
    AnomalyStorageWriteResult,
    DatabaseSchemaResult,
    DatasetStorageError,
    StorageErrorCode,
    StorageWriteResult,
    StoredRecord,
    StoredAnomaly,
    count_stored_records,
    initialize_database,
    persist_validated_dataset,
    persist_reconciliation_result,
    read_stored_anomalies,
    read_stored_records,
    update_anomaly_status,
)

__all__ = [
    "ANOMALY_TABLE",
    "STORAGE_TABLES",
    "AnomalyStorageWriteResult",
    "DatabaseSchemaResult",
    "DatasetStorageError",
    "StorageErrorCode",
    "StorageWriteResult",
    "StoredRecord",
    "StoredAnomaly",
    "count_stored_records",
    "initialize_database",
    "persist_validated_dataset",
    "persist_reconciliation_result",
    "read_stored_anomalies",
    "read_stored_records",
    "update_anomaly_status",
]
