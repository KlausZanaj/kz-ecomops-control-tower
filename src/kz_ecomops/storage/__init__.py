"""Public API for local idempotent SQLite persistence."""

from .sqlite import (
    STORAGE_TABLES,
    DatabaseSchemaResult,
    DatasetStorageError,
    StorageErrorCode,
    StorageWriteResult,
    StoredRecord,
    count_stored_records,
    initialize_database,
    persist_validated_dataset,
    read_stored_records,
)

__all__ = [
    "STORAGE_TABLES",
    "DatabaseSchemaResult",
    "DatasetStorageError",
    "StorageErrorCode",
    "StorageWriteResult",
    "StoredRecord",
    "count_stored_records",
    "initialize_database",
    "persist_validated_dataset",
    "read_stored_records",
]
