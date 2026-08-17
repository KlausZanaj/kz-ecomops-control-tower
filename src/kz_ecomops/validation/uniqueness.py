"""Blocking within-file uniqueness validation for normalized CSV data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from .schemas import CsvSchema
from .values import CsvValueValidationResult


class CsvUniquenessErrorCode(StrEnum):
    """Stable codes for blocking within-file uniqueness errors."""

    DUPLICATE_ORDER_ID = "duplicate_order_id"
    DUPLICATE_SOURCE_ORDER_KEY = "duplicate_source_order_key"
    DUPLICATE_SHIPMENT_ID = "duplicate_shipment_id"
    DUPLICATE_RETURN_ID = "duplicate_return_id"


@dataclass(frozen=True, slots=True)
class CsvUniquenessIssue:
    """Describe one complete group of duplicate rows without retaining its key."""

    code: CsvUniquenessErrorCode
    filename: str
    row_numbers: tuple[int, ...]
    columns: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class CsvUniquenessValidationResult:
    """Summarize blocking within-file uniqueness validation."""

    schema: CsvSchema
    row_count: int
    issues: tuple[CsvUniquenessIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Return whether no blocking duplicate group was found."""

        return not self.issues

    @property
    def issue_count(self) -> int:
        """Return the number of duplicate groups across all rules."""

        return len(self.issues)

    @property
    def invalid_row_numbers(self) -> frozenset[int]:
        """Return every positional data-row number in a duplicate group."""

        return frozenset(
            row_number
            for issue in self.issues
            for row_number in issue.row_numbers
        )

    @property
    def invalid_row_count(self) -> int:
        """Return the number of distinct rows in duplicate groups."""

        return len(self.invalid_row_numbers)

    @property
    def valid_row_count(self) -> int:
        """Return the number of rows outside blocking duplicate groups."""

        return self.row_count - self.invalid_row_count


def _duplicate_groups(
    dataframe: pd.DataFrame,
    columns: tuple[str, ...],
) -> tuple[tuple[int, ...], ...]:
    column_positions = tuple(
        dataframe.columns.get_loc(column) for column in columns
    )
    grouped_rows: dict[tuple[str, ...], list[int]] = {}

    for row_position in range(len(dataframe)):
        key = tuple(
            dataframe.iloc[row_position, column_position]
            for column_position in column_positions
        )
        grouped_rows.setdefault(key, []).append(row_position + 1)

    return tuple(
        tuple(row_numbers)
        for row_numbers in grouped_rows.values()
        if len(row_numbers) > 1
    )


def _issues_for_rule(
    dataframe: pd.DataFrame,
    schema: CsvSchema,
    code: CsvUniquenessErrorCode,
    columns: tuple[str, ...],
) -> tuple[CsvUniquenessIssue, ...]:
    issues: list[CsvUniquenessIssue] = []
    for row_numbers in _duplicate_groups(dataframe, columns):
        issues.append(
            CsvUniquenessIssue(
                code=code,
                filename=schema.filename,
                row_numbers=row_numbers,
                columns=columns,
                message=(
                    f"CSV file {schema.filename!r}, data rows "
                    f"{', '.join(str(row) for row in row_numbers)}, column(s) "
                    f"{', '.join(repr(column) for column in columns)}: a duplicate "
                    "group violates a blocking uniqueness rule. Correct the source "
                    "records so this key is unique."
                ),
            )
        )
    return tuple(issues)


def _validate_preconditions(
    dataframe: pd.DataFrame,
    schema: CsvSchema,
    value_result: CsvValueValidationResult,
) -> None:
    prerequisite_message = (
        "Value validation must complete successfully before uniqueness validation."
    )
    if value_result.schema != schema:
        raise ValueError(
            f"value_result uses a different CSV schema. {prerequisite_message}"
        )
    if value_result.row_count != len(dataframe):
        raise ValueError(
            f"value_result has a different row count. {prerequisite_message}"
        )
    if not value_result.is_valid:
        raise ValueError(
            f"value_result contains cell validation issues. {prerequisite_message}"
        )


def validate_csv_uniqueness(
    dataframe: pd.DataFrame,
    schema: CsvSchema,
    value_result: CsvValueValidationResult,
) -> CsvUniquenessValidationResult:
    """Validate only blocking uniqueness rules after successful value validation."""

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError(
            "dataframe must be a pandas DataFrame. Value validation must complete "
            "successfully before uniqueness validation."
        )
    if not isinstance(value_result, CsvValueValidationResult):
        raise TypeError(
            "value_result must be a CsvValueValidationResult. Value validation "
            "must complete successfully before uniqueness validation."
        )

    _validate_preconditions(dataframe, schema, value_result)

    issues: list[CsvUniquenessIssue] = []
    if schema.filename == "orders.csv":
        issues.extend(
            _issues_for_rule(
                dataframe,
                schema,
                CsvUniquenessErrorCode.DUPLICATE_ORDER_ID,
                ("order_id",),
            )
        )
        issues.extend(
            _issues_for_rule(
                dataframe,
                schema,
                CsvUniquenessErrorCode.DUPLICATE_SOURCE_ORDER_KEY,
                ("platform", "source_order_id"),
            )
        )
    elif schema.filename == "shipments.csv":
        issues.extend(
            _issues_for_rule(
                dataframe,
                schema,
                CsvUniquenessErrorCode.DUPLICATE_SHIPMENT_ID,
                ("shipment_id",),
            )
        )
    elif schema.filename == "returns.csv":
        issues.extend(
            _issues_for_rule(
                dataframe,
                schema,
                CsvUniquenessErrorCode.DUPLICATE_RETURN_ID,
                ("return_id",),
            )
        )

    return CsvUniquenessValidationResult(
        schema=schema,
        row_count=len(dataframe),
        issues=tuple(issues),
    )
