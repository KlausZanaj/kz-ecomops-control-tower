"""End-to-end orchestration for the five required normalized CSV files."""

from __future__ import annotations

from pathlib import Path

from .integrity import CsvIntegrityValidationResult, validate_csv_integrity
from .reader import CsvReadResult, read_csv_file
from .relationships import (
    CsvRelationshipValidationResult,
    validate_csv_relationships,
)
from .report import (
    DatasetValidationReport,
    DatasetValidationResult,
    FileValidationReport,
    ValidationMessage,
    ValidationStage,
)
from .schemas import CSV_SCHEMAS
from .uniqueness import (
    CsvUniquenessValidationResult,
    validate_csv_uniqueness,
)
from .values import CsvValueValidationResult, validate_csv_values


def _read_messages(result: CsvReadResult) -> list[ValidationMessage]:
    return [
        ValidationMessage(
            stage=ValidationStage.READ,
            code=issue.code.value,
            filename=result.schema.filename,
            row_numbers=(),
            columns=issue.columns,
            message=issue.message,
            blocking=True,
        )
        for issue in result.issues
    ]


def _value_messages(result: CsvValueValidationResult) -> list[ValidationMessage]:
    return [
        ValidationMessage(
            stage=ValidationStage.VALUE,
            code=issue.code.value,
            filename=result.schema.filename,
            row_numbers=(issue.row_number,),
            columns=(issue.column,),
            message=issue.message,
            blocking=True,
        )
        for issue in result.issues
    ]


def _integrity_messages(
    result: CsvIntegrityValidationResult,
) -> list[ValidationMessage]:
    return [
        ValidationMessage(
            stage=ValidationStage.INTEGRITY,
            code=issue.code.value,
            filename=result.schema.filename,
            row_numbers=(issue.row_number,),
            columns=issue.columns,
            message=issue.message,
            blocking=True,
        )
        for issue in result.issues
    ]


def _uniqueness_messages(
    result: CsvUniquenessValidationResult,
) -> list[ValidationMessage]:
    return [
        ValidationMessage(
            stage=ValidationStage.UNIQUENESS,
            code=issue.code.value,
            filename=result.schema.filename,
            row_numbers=issue.row_numbers,
            columns=issue.columns,
            message=issue.message,
            blocking=True,
        )
        for issue in result.issues
    ]


def _relationship_messages(
    result: CsvRelationshipValidationResult,
) -> list[ValidationMessage]:
    return [
        ValidationMessage(
            stage=ValidationStage.RELATIONSHIP,
            code=finding.code.value,
            filename=finding.filename,
            row_numbers=(finding.row_number,),
            columns=finding.columns,
            message=finding.message,
            blocking=False,
        )
        for finding in result.findings
    ]


def validate_dataset_directory(directory: str | Path) -> DatasetValidationResult:
    """Run the complete ordered validation pipeline for one dataset directory."""

    dataset_directory = Path(directory)
    if not dataset_directory.exists():
        raise ValueError(
            f"Dataset directory {str(dataset_directory)!r} does not exist."
        )
    if not dataset_directory.is_dir():
        raise ValueError(
            f"Dataset path {str(dataset_directory)!r} is not a directory."
        )

    dataframes = {}
    value_results: dict[str, CsvValueValidationResult] = {}
    integrity_results: dict[str, CsvIntegrityValidationResult] = {}
    uniqueness_results: dict[str, CsvUniquenessValidationResult] = {}
    messages_by_file: dict[str, list[ValidationMessage]] = {
        filename: [] for filename in CSV_SCHEMAS
    }
    row_counts: dict[str, int] = {filename: 0 for filename in CSV_SCHEMAS}
    rejected_rows: dict[str, set[int]] = {
        filename: set() for filename in CSV_SCHEMAS
    }

    for filename, schema in CSV_SCHEMAS.items():
        read_result = read_csv_file(dataset_directory / filename, schema)
        messages_by_file[filename].extend(_read_messages(read_result))
        if not read_result.is_valid:
            continue

        dataframe = read_result.dataframe
        assert dataframe is not None
        dataframes[filename] = dataframe
        row_counts[filename] = read_result.row_count

        value_result = validate_csv_values(dataframe, schema)
        value_results[filename] = value_result
        value_messages = _value_messages(value_result)
        messages_by_file[filename].extend(value_messages)
        rejected_rows[filename].update(
            row_number
            for message in value_messages
            for row_number in message.row_numbers
        )
        if not value_result.is_valid:
            continue

        integrity_result = validate_csv_integrity(dataframe, schema, value_result)
        uniqueness_result = validate_csv_uniqueness(dataframe, schema, value_result)
        integrity_results[filename] = integrity_result
        uniqueness_results[filename] = uniqueness_result

        integrity_messages = _integrity_messages(integrity_result)
        uniqueness_messages = _uniqueness_messages(uniqueness_result)
        messages_by_file[filename].extend(integrity_messages)
        messages_by_file[filename].extend(uniqueness_messages)
        rejected_rows[filename].update(
            row_number
            for message in (*integrity_messages, *uniqueness_messages)
            for row_number in message.row_numbers
        )

    has_blocking_messages = any(
        message.blocking
        for filename in CSV_SCHEMAS
        for message in messages_by_file[filename]
    )
    if not has_blocking_messages:
        relationship_result = validate_csv_relationships(
            dataframes,
            value_results,
            integrity_results,
            uniqueness_results,
        )
        for message in _relationship_messages(relationship_result):
            messages_by_file[message.filename].append(message)

    file_reports = tuple(
        FileValidationReport(
            filename=filename,
            row_count=row_counts[filename],
            accepted_row_count=(
                row_counts[filename] - len(rejected_rows[filename])
            ),
            rejected_row_count=len(rejected_rows[filename]),
            messages=tuple(messages_by_file[filename]),
        )
        for filename in CSV_SCHEMAS
    )
    report = DatasetValidationReport(files=file_reports)
    return DatasetValidationResult(
        report=report,
        dataframes=dataframes if not has_blocking_messages else None,
    )
