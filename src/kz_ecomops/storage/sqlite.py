"""Transactional idempotent SQLite storage for validated canonical datasets.

Cross-file foreign keys are intentionally omitted so non-blocking orphan records
remain available to the REC-10 reconciliation rule.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

import pandas as pd

from kz_ecomops.validation import CSV_SCHEMAS, DatasetValidationResult
from kz_ecomops.reconciliation import (
    AnomalyCode,
    ProblemType,
    RecordReference,
    ReconciliationAnomaly,
    ReconciliationResult,
    ReviewStatus,
    RuleCode,
    Severity,
)


STORAGE_TABLES: Mapping[str, str] = MappingProxyType(
    {filename: filename.removesuffix(".csv") for filename in CSV_SCHEMAS}
)
ANOMALY_TABLE = "reconciliation_anomalies"


class StorageErrorCode(StrEnum):
    """Stable codes for rejected or failed storage operations."""

    INVALID_RESULT = "invalid_result"
    INCOMPLETE_DATASET = "incomplete_dataset"
    NOT_RECONCILIATION_READY = "not_reconciliation_ready"
    CONFLICTING_RECORD = "conflicting_record"
    DATABASE_ERROR = "database_error"


class DatasetStorageError(ValueError):
    """Report one safe storage failure with a stable public code."""

    def __init__(self, code: StorageErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DatabaseSchemaResult:
    """Describe the initialized local database schema."""

    database_path: Path
    tables: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StorageWriteResult:
    """Summarize inserted and idempotently existing records by CSV filename."""

    inserted_counts: Mapping[str, int]
    existing_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "inserted_counts", MappingProxyType(dict(self.inserted_counts))
        )
        object.__setattr__(
            self, "existing_counts", MappingProxyType(dict(self.existing_counts))
        )

    @property
    def inserted_total(self) -> int:
        return sum(self.inserted_counts.values())

    @property
    def existing_total(self) -> int:
        return sum(self.existing_counts.values())


@dataclass(frozen=True, slots=True)
class StoredRecord:
    """Expose one stored row with deterministic traceability metadata."""

    record_key: str
    source_row_number: int
    values: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass(frozen=True, slots=True)
class AnomalyStorageWriteResult:
    """Summarize inserted and idempotently existing anomaly records."""

    inserted_count: int
    existing_count: int


@dataclass(frozen=True, slots=True)
class StoredAnomaly:
    """Expose one persisted anomaly with detection-history timestamps."""

    anomaly: ReconciliationAnomaly
    first_detected_at: datetime
    last_detected_at: datetime


def _quoted(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def _table_statement(filename: str) -> str:
    schema = CSV_SCHEMAS[filename]
    table = STORAGE_TABLES[filename]
    columns = [
        '"_record_key" TEXT PRIMARY KEY',
        '"_source_row_number" INTEGER NOT NULL',
        *(_quoted(column.name) + " TEXT NOT NULL" for column in schema.columns),
    ]
    if filename == "orders.csv":
        columns.extend(
            (
                'UNIQUE ("order_id")',
                'UNIQUE ("platform", "source_order_id")',
            )
        )
    elif filename == "shipments.csv":
        columns.append('UNIQUE ("shipment_id")')
    elif filename == "returns.csv":
        columns.append('UNIQUE ("return_id")')
    return f"CREATE TABLE IF NOT EXISTS {_quoted(table)} ({', '.join(columns)})"


def _create_schema(connection: sqlite3.Connection) -> None:
    for filename in CSV_SCHEMAS:
        connection.execute(_table_statement(filename))


def _create_anomaly_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_quoted(ANOMALY_TABLE)} (
            "anomaly_id" TEXT PRIMARY KEY,
            "rule_code" TEXT NOT NULL,
            "anomaly_code" TEXT NOT NULL,
            "order_id" TEXT,
            "platform" TEXT NOT NULL,
            "problem_type" TEXT NOT NULL,
            "description" TEXT NOT NULL,
            "severity" TEXT NOT NULL,
            "detected_at" TEXT NOT NULL,
            "recommended_action" TEXT NOT NULL,
            "review_status" TEXT NOT NULL CHECK (
                "review_status" IN ('open', 'in_review', 'resolved', 'dismissed')
            ),
            "compared_values_json" TEXT NOT NULL,
            "record_references_json" TEXT NOT NULL,
            "first_detected_at" TEXT NOT NULL,
            "last_detected_at" TEXT NOT NULL
        )
        """
    )


def initialize_database(database_path: str | Path) -> DatabaseSchemaResult:
    """Create the five canonical tables using one SQLite transaction."""

    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as connection:
            _create_schema(connection)
    except sqlite3.Error as error:
        raise DatasetStorageError(
            StorageErrorCode.DATABASE_ERROR,
            "The SQLite schema could not be initialized safely.",
        ) from error
    return DatabaseSchemaResult(
        database_path=path,
        tables=tuple(STORAGE_TABLES.values()),
    )


def _validate_result(result: object) -> DatasetValidationResult:
    if not isinstance(result, DatasetValidationResult):
        raise TypeError("result must be a DatasetValidationResult.")
    if not result.report.reconciliation_ready or result.report.blocking_message_count:
        raise DatasetStorageError(
            StorageErrorCode.NOT_RECONCILIATION_READY,
            "Only a reconciliation-ready dataset without blocking messages can be stored.",
        )
    if result.dataframes is None:
        raise DatasetStorageError(
            StorageErrorCode.INCOMPLETE_DATASET,
            "The validated dataset does not expose all five canonical DataFrames.",
        )
    if set(result.dataframes) != set(CSV_SCHEMAS):
        raise DatasetStorageError(
            StorageErrorCode.INCOMPLETE_DATASET,
            "The validated dataset must contain exactly the five canonical DataFrames.",
        )
    for filename, schema in CSV_SCHEMAS.items():
        dataframe = result.dataframes[filename]
        if not isinstance(dataframe, pd.DataFrame):
            raise DatasetStorageError(
                StorageErrorCode.INCOMPLETE_DATASET,
                "Every canonical dataset entry must be a pandas DataFrame.",
            )
        if dataframe.columns.has_duplicates:
            raise DatasetStorageError(
                StorageErrorCode.INCOMPLETE_DATASET,
                "Canonical DataFrame column names must not be duplicated.",
            )
        available_columns = set(dataframe.columns)
        missing_required_columns = tuple(
            column.name
            for column in schema.required_columns
            if column.name not in available_columns
        )
        if missing_required_columns:
            raise DatasetStorageError(
                StorageErrorCode.INCOMPLETE_DATASET,
                "Every canonical DataFrame must contain all required schema columns.",
            )
        file_report = result.report.get_file(filename)
        if (
            file_report.row_count != len(dataframe)
            or file_report.rejected_row_count
            or file_report.accepted_row_count != len(dataframe)
        ):
            raise DatasetStorageError(
                StorageErrorCode.INVALID_RESULT,
                "Validation report counts do not match the canonical DataFrames.",
            )
        stored_columns = tuple(
            column
            for column in schema.column_names
            if column in available_columns
        )
        if any(
            not isinstance(value, str)
            for value in dataframe.loc[:, stored_columns].to_numpy().ravel()
        ):
            raise DatasetStorageError(
                StorageErrorCode.INVALID_RESULT,
                "Canonical DataFrame values must remain strings before storage.",
            )
    return result


def _record_payload(filename: str, values: tuple[str, ...]) -> str:
    return json.dumps(
        {"filename": filename, "values": values},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _record_key(payload: str, occurrence: int) -> str:
    material = f"{payload}\u0000{occurrence}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _insert_dataframe(
    connection: sqlite3.Connection,
    filename: str,
    dataframe: pd.DataFrame,
) -> tuple[int, int]:
    table = STORAGE_TABLES[filename]
    canonical_columns = CSV_SCHEMAS[filename].column_names
    insert_columns = ("_record_key", "_source_row_number", *canonical_columns)
    placeholders = ", ".join("?" for _ in insert_columns)
    statement = (
        f"INSERT OR IGNORE INTO {_quoted(table)} "
        f"({', '.join(_quoted(column) for column in insert_columns)}) "
        f"VALUES ({placeholders})"
    )
    payload_occurrences: dict[str, int] = {}
    inserted = 0
    existing = 0
    for row_position in range(len(dataframe)):
        values = tuple(
            (
                dataframe.iloc[row_position, dataframe.columns.get_loc(column)]
                if column in dataframe.columns
                else ""
            )
            for column in canonical_columns
        )
        payload = _record_payload(filename, values)
        occurrence = payload_occurrences.get(payload, 0) + 1
        payload_occurrences[payload] = occurrence
        record_key = _record_key(payload, occurrence)
        cursor = connection.execute(
            statement,
            (record_key, row_position + 1, *values),
        )
        if cursor.rowcount == 1:
            inserted += 1
            continue
        matching_key = connection.execute(
            f"SELECT 1 FROM {_quoted(table)} WHERE \"_record_key\" = ?",
            (record_key,),
        ).fetchone()
        if matching_key is None:
            raise DatasetStorageError(
                StorageErrorCode.CONFLICTING_RECORD,
                "A unique canonical identifier already belongs to different record content.",
            )
        existing += 1
    return inserted, existing


def persist_validated_dataset(
    database_path: str | Path,
    result: DatasetValidationResult,
) -> StorageWriteResult:
    """Persist a complete valid dataset atomically and idempotently."""

    checked_result = _validate_result(result)
    assert checked_result.dataframes is not None
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    inserted_counts: dict[str, int] = {}
    existing_counts: dict[str, int] = {}
    try:
        with sqlite3.connect(path) as connection:
            _create_schema(connection)
            for filename in CSV_SCHEMAS:
                inserted, existing = _insert_dataframe(
                    connection,
                    filename,
                    checked_result.dataframes[filename],
                )
                inserted_counts[filename] = inserted
                existing_counts[filename] = existing
    except DatasetStorageError:
        raise
    except sqlite3.Error as error:
        raise DatasetStorageError(
            StorageErrorCode.DATABASE_ERROR,
            "The SQLite transaction failed and was rolled back.",
        ) from error
    return StorageWriteResult(
        inserted_counts=inserted_counts,
        existing_counts=existing_counts,
    )


def count_stored_records(database_path: str | Path) -> Mapping[str, int]:
    """Return protected record counts for the five canonical tables."""

    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database {str(path)!r} does not exist.")
    try:
        with sqlite3.connect(path) as connection:
            counts = {
                filename: connection.execute(
                    f"SELECT COUNT(*) FROM {_quoted(table)}"
                ).fetchone()[0]
                for filename, table in STORAGE_TABLES.items()
            }
    except sqlite3.Error as error:
        raise DatasetStorageError(
            StorageErrorCode.DATABASE_ERROR,
            "Stored record counts could not be read safely.",
        ) from error
    return MappingProxyType(counts)


def read_stored_records(
    database_path: str | Path,
    filename: str,
) -> tuple[StoredRecord, ...]:
    """Read one canonical table in source-row order for verification."""

    if filename not in CSV_SCHEMAS:
        raise KeyError(f"No storage table is registered for {filename!r}.")
    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database {str(path)!r} does not exist.")
    table = STORAGE_TABLES[filename]
    columns = CSV_SCHEMAS[filename].column_names
    selected = ("_record_key", "_source_row_number", *columns)
    try:
        with sqlite3.connect(path) as connection:
            rows = connection.execute(
                f"SELECT {', '.join(_quoted(column) for column in selected)} "
                f"FROM {_quoted(table)} "
                'ORDER BY "_source_row_number", "_record_key"'
            ).fetchall()
    except sqlite3.Error as error:
        raise DatasetStorageError(
            StorageErrorCode.DATABASE_ERROR,
            "Stored canonical records could not be read safely.",
        ) from error
    return tuple(
        StoredRecord(
            record_key=row[0],
            source_row_number=row[1],
            values=dict(zip(columns, row[2:], strict=True)),
        )
        for row in rows
    )


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _compared_values_json(anomaly: ReconciliationAnomaly) -> str:
    return json.dumps(
        dict(anomaly.compared_values),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _record_references_json(anomaly: ReconciliationAnomaly) -> str:
    return json.dumps(
        [
            {
                "filename": reference.filename,
                "record_id": reference.record_id,
                "row_number": reference.row_number,
            }
            for reference in anomaly.record_references
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _anomaly_values(anomaly: ReconciliationAnomaly) -> tuple[str | None, ...]:
    detected_at = _utc_text(anomaly.detected_at)
    return (
        anomaly.anomaly_id,
        anomaly.rule_code.value,
        anomaly.anomaly_code.value,
        anomaly.order_id,
        anomaly.platform,
        anomaly.problem_type.value,
        anomaly.description,
        anomaly.severity.value,
        detected_at,
        anomaly.recommended_action,
        anomaly.review_status.value,
        _compared_values_json(anomaly),
        _record_references_json(anomaly),
        detected_at,
        detected_at,
    )


def persist_reconciliation_result(
    database_path: str | Path,
    result: ReconciliationResult,
) -> AnomalyStorageWriteResult:
    """Atomically upsert deterministic anomalies while preserving review states."""

    if not isinstance(result, ReconciliationResult):
        raise TypeError("result must be a ReconciliationResult.")
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = (
        "anomaly_id",
        "rule_code",
        "anomaly_code",
        "order_id",
        "platform",
        "problem_type",
        "description",
        "severity",
        "detected_at",
        "recommended_action",
        "review_status",
        "compared_values_json",
        "record_references_json",
        "first_detected_at",
        "last_detected_at",
    )
    placeholders = ", ".join("?" for _ in columns)
    update_columns = (
        "rule_code",
        "anomaly_code",
        "order_id",
        "platform",
        "problem_type",
        "description",
        "severity",
        "detected_at",
        "recommended_action",
        "compared_values_json",
        "record_references_json",
    )
    updates = ", ".join(
        f"{_quoted(column)} = excluded.{_quoted(column)}"
        for column in update_columns
    )
    statement = (
        f"INSERT INTO {_quoted(ANOMALY_TABLE)} "
        f"({', '.join(_quoted(column) for column in columns)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT({_quoted('anomaly_id')}) DO UPDATE SET {updates}, "
        '"first_detected_at" = MIN("first_detected_at", excluded."first_detected_at"), '
        '"last_detected_at" = MAX("last_detected_at", excluded."last_detected_at")'
    )
    inserted = 0
    existing = 0
    try:
        with sqlite3.connect(path) as connection:
            _create_schema(connection)
            _create_anomaly_schema(connection)
            for anomaly in result.anomalies:
                already_exists = connection.execute(
                    f"SELECT 1 FROM {_quoted(ANOMALY_TABLE)} WHERE \"anomaly_id\" = ?",
                    (anomaly.anomaly_id,),
                ).fetchone()
                connection.execute(statement, _anomaly_values(anomaly))
                if already_exists is None:
                    inserted += 1
                else:
                    existing += 1
    except sqlite3.Error as error:
        raise DatasetStorageError(
            StorageErrorCode.DATABASE_ERROR,
            "The anomaly transaction failed and was rolled back.",
        ) from error
    return AnomalyStorageWriteResult(inserted, existing)


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def read_stored_anomalies(
    database_path: str | Path,
) -> tuple[StoredAnomaly, ...]:
    """Read stored anomalies in deterministic rule and source-reference order."""

    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database {str(path)!r} does not exist.")
    selected = (
        "anomaly_id",
        "rule_code",
        "anomaly_code",
        "order_id",
        "platform",
        "problem_type",
        "description",
        "severity",
        "detected_at",
        "recommended_action",
        "review_status",
        "compared_values_json",
        "record_references_json",
        "first_detected_at",
        "last_detected_at",
    )
    try:
        with sqlite3.connect(path) as connection:
            rows = connection.execute(
                f"SELECT {', '.join(_quoted(column) for column in selected)} "
                f"FROM {_quoted(ANOMALY_TABLE)} "
                'ORDER BY "rule_code", "platform", COALESCE("order_id", \'\'), '
                '"record_references_json", "anomaly_id"'
            ).fetchall()
    except sqlite3.Error as error:
        raise DatasetStorageError(
            StorageErrorCode.DATABASE_ERROR,
            "Stored reconciliation anomalies could not be read safely.",
        ) from error

    stored: list[StoredAnomaly] = []
    for row in rows:
        compared_values = json.loads(row[11])
        references = tuple(
            RecordReference(
                filename=item["filename"],
                row_number=item["row_number"],
                record_id=item["record_id"],
            )
            for item in json.loads(row[12])
        )
        anomaly = ReconciliationAnomaly(
            anomaly_id=row[0],
            rule_code=RuleCode(row[1]),
            anomaly_code=AnomalyCode(row[2]),
            order_id=row[3],
            platform=row[4],
            problem_type=ProblemType(row[5]),
            description=row[6],
            severity=Severity(row[7]),
            detected_at=_parse_datetime(row[8]),
            recommended_action=row[9],
            review_status=ReviewStatus(row[10]),
            compared_values=compared_values,
            record_references=references,
        )
        stored.append(
            StoredAnomaly(
                anomaly=anomaly,
                first_detected_at=_parse_datetime(row[13]),
                last_detected_at=_parse_datetime(row[14]),
            )
        )
    return tuple(stored)


def update_anomaly_status(
    database_path: str | Path,
    anomaly_id: str,
    review_status: ReviewStatus | str,
) -> StoredAnomaly:
    """Update one human review state without changing detected anomaly data."""

    if not anomaly_id:
        raise ValueError("anomaly_id must not be empty.")
    try:
        checked_status = (
            review_status
            if isinstance(review_status, ReviewStatus)
            else ReviewStatus(review_status)
        )
    except (TypeError, ValueError) as error:
        raise ValueError("review_status is not a supported review state.") from error
    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database {str(path)!r} does not exist.")
    try:
        with sqlite3.connect(path) as connection:
            cursor = connection.execute(
                f"UPDATE {_quoted(ANOMALY_TABLE)} SET \"review_status\" = ? "
                'WHERE "anomaly_id" = ?',
                (checked_status.value, anomaly_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"No stored anomaly exists for ID {anomaly_id!r}.")
    except KeyError:
        raise
    except sqlite3.Error as error:
        raise DatasetStorageError(
            StorageErrorCode.DATABASE_ERROR,
            "The anomaly review status could not be updated safely.",
        ) from error
    return next(
        stored
        for stored in read_stored_anomalies(path)
        if stored.anomaly.anomaly_id == anomaly_id
    )
