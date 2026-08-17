"""Cell-level validation for structurally valid normalized CSV data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

import pandas as pd

from .schemas import ColumnSchema, CsvSchema, DataType


class CsvValueErrorCode(StrEnum):
    """Stable codes for individual CSV cell validation errors."""

    MISSING_REQUIRED_VALUE = "missing_required_value"
    DISALLOWED_MISSING_MARKER = "disallowed_missing_marker"
    NON_STRING_VALUE = "non_string_value"
    INVALID_ALLOWED_VALUE = "invalid_allowed_value"
    INVALID_DECIMAL = "invalid_decimal"
    MINIMUM_VIOLATION = "minimum_violation"
    INVALID_DATETIME = "invalid_datetime"


@dataclass(frozen=True, slots=True)
class CsvValueIssue:
    """Describe one invalid cell without retaining its original value."""

    code: CsvValueErrorCode
    filename: str
    row_number: int
    column: str
    message: str


@dataclass(frozen=True, slots=True)
class CsvValueValidationResult:
    """Summarize cell-level validation without returning transformed data."""

    schema: CsvSchema
    row_count: int
    issues: tuple[CsvValueIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Return whether every validated cell is valid."""

        return not self.issues

    @property
    def issue_count(self) -> int:
        """Return the number of individual invalid cells."""

        return len(self.issues)

    @property
    def invalid_row_numbers(self) -> frozenset[int]:
        """Return positional data-row numbers containing at least one issue."""

        return frozenset(issue.row_number for issue in self.issues)

    @property
    def invalid_row_count(self) -> int:
        """Return the number of rows containing at least one issue."""

        return len(self.invalid_row_numbers)

    @property
    def valid_row_count(self) -> int:
        """Return the number of rows without issues."""

        return self.row_count - self.invalid_row_count


_DISALLOWED_MISSING_MARKERS = frozenset({"n/a", "null", "-"})
_PLAIN_DECIMAL_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
_DATETIME_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)"
)


def _issue(
    code: CsvValueErrorCode,
    schema: CsvSchema,
    row_number: int,
    column: ColumnSchema,
    explanation: str,
) -> CsvValueIssue:
    return CsvValueIssue(
        code=code,
        filename=schema.filename,
        row_number=row_number,
        column=column.name,
        message=(
            f"CSV file {schema.filename!r}, data row {row_number}, "
            f"column {column.name!r}: {explanation}"
        ),
    )


def _decimal_issue(
    value: str,
    schema: CsvSchema,
    row_number: int,
    column: ColumnSchema,
) -> CsvValueIssue | None:
    if column.decimal_places is None:
        decimal_shape_is_valid = _PLAIN_DECIMAL_PATTERN.fullmatch(value) is not None
        precision_instruction = "Use plain decimal notation with a point separator."
    else:
        decimal_shape_is_valid = (
            re.fullmatch(rf"-?\d+\.\d{{{column.decimal_places}}}", value)
            is not None
        )
        precision_instruction = (
            f"Use plain decimal notation with exactly {column.decimal_places} "
            "digit(s) after the point."
        )

    if not decimal_shape_is_valid:
        return _issue(
            CsvValueErrorCode.INVALID_DECIMAL,
            schema,
            row_number,
            column,
            f"the value is not a supported finite decimal. {precision_instruction}",
        )

    try:
        decimal_value = Decimal(value)
    except InvalidOperation:
        return _issue(
            CsvValueErrorCode.INVALID_DECIMAL,
            schema,
            row_number,
            column,
            f"the value is not a supported finite decimal. {precision_instruction}",
        )

    if not decimal_value.is_finite():
        return _issue(
            CsvValueErrorCode.INVALID_DECIMAL,
            schema,
            row_number,
            column,
            f"the value is not a supported finite decimal. {precision_instruction}",
        )

    if column.minimum is None:
        return None

    minimum_is_satisfied = (
        decimal_value >= column.minimum
        if column.minimum_inclusive
        else decimal_value > column.minimum
    )
    if minimum_is_satisfied:
        return None

    comparison = "greater than or equal to" if column.minimum_inclusive else "greater than"
    return _issue(
        CsvValueErrorCode.MINIMUM_VIOLATION,
        schema,
        row_number,
        column,
        f"the value is below the permitted minimum. Use a value {comparison} the documented minimum.",
    )


def _datetime_issue(
    value: str,
    schema: CsvSchema,
    row_number: int,
    column: ColumnSchema,
) -> CsvValueIssue | None:
    if _DATETIME_PATTERN.fullmatch(value) is None:
        return _issue(
            CsvValueErrorCode.INVALID_DATETIME,
            schema,
            row_number,
            column,
            (
                "the value is not a supported ISO 8601 date-time. Use "
                "YYYY-MM-DDTHH:MM:SS with Z or a ±HH:MM offset."
            ),
        )

    try:
        parsed_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return _issue(
            CsvValueErrorCode.INVALID_DATETIME,
            schema,
            row_number,
            column,
            (
                "the value is not a real calendar date-time. Use a valid "
                "ISO 8601 date-time with a timezone."
            ),
        )

    if parsed_value.tzinfo is None or parsed_value.utcoffset() is None:
        return _issue(
            CsvValueErrorCode.INVALID_DATETIME,
            schema,
            row_number,
            column,
            "the date-time has no timezone. Add Z or a valid ±HH:MM offset.",
        )

    return None


def _validate_cell(
    value: object,
    schema: CsvSchema,
    row_number: int,
    column: ColumnSchema,
) -> CsvValueIssue | None:
    if not isinstance(value, str):
        return _issue(
            CsvValueErrorCode.NON_STRING_VALUE,
            schema,
            row_number,
            column,
            (
                "the value is not text. Load CSV data with read_csv_file or "
                "provide the cell as a string."
            ),
        )

    stripped_value = value.strip()
    if not stripped_value:
        if column.required:
            return _issue(
                CsvValueErrorCode.MISSING_REQUIRED_VALUE,
                schema,
                row_number,
                column,
                "the required value is empty. Provide the documented value.",
            )
        return None

    if stripped_value.casefold() in _DISALLOWED_MISSING_MARKERS:
        return _issue(
            CsvValueErrorCode.DISALLOWED_MISSING_MARKER,
            schema,
            row_number,
            column,
            (
                "the cell uses a disallowed missing-value marker. Leave an "
                "optional cell empty or provide a valid value."
            ),
        )

    if column.allowed_values is not None and value not in column.allowed_values:
        return _issue(
            CsvValueErrorCode.INVALID_ALLOWED_VALUE,
            schema,
            row_number,
            column,
            "the value is not an allowed exact option. Use a documented value with matching case.",
        )

    if column.data_type is DataType.DECIMAL:
        return _decimal_issue(value, schema, row_number, column)

    if column.data_type is DataType.DATETIME:
        return _datetime_issue(value, schema, row_number, column)

    return None


def validate_csv_values(
    dataframe: pd.DataFrame,
    schema: CsvSchema,
) -> CsvValueValidationResult:
    """Validate individual cells without modifying or returning normalized data."""

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe must be a pandas DataFrame.")

    if dataframe.columns.has_duplicates:
        raise ValueError(
            f"DataFrame for {schema.filename!r} has duplicate column names. "
            "Run structural CSV validation before value validation."
        )

    available_columns = set(dataframe.columns)
    missing_columns = tuple(
        column.name
        for column in schema.required_columns
        if column.name not in available_columns
    )
    if missing_columns:
        raise ValueError(
            f"DataFrame for {schema.filename!r} is missing required column(s): "
            f"{', '.join(missing_columns)}. Run structural CSV validation before "
            "value validation."
        )

    columns_to_validate = tuple(
        column for column in schema.columns if column.name in available_columns
    )
    column_positions = {
        column.name: dataframe.columns.get_loc(column.name)
        for column in columns_to_validate
    }
    issues: list[CsvValueIssue] = []

    for row_position in range(len(dataframe)):
        row_number = row_position + 1
        for column in columns_to_validate:
            value = dataframe.iloc[row_position, column_positions[column.name]]
            issue = _validate_cell(value, schema, row_number, column)
            if issue is not None:
                issues.append(issue)

    return CsvValueValidationResult(
        schema=schema,
        row_count=len(dataframe),
        issues=tuple(issues),
    )
