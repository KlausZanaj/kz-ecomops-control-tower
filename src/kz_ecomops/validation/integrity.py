"""Row-level integrity validation for value-valid normalized CSV data."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

import pandas as pd

from .schemas import CsvSchema
from .values import CsvValueValidationResult


DEFAULT_MONETARY_TOLERANCE = Decimal("0.01")


class CsvIntegrityErrorCode(StrEnum):
    """Stable codes for row-level CSV integrity errors."""

    ORDER_ID_MISMATCH = "order_id_mismatch"
    ORDER_TOTAL_MISMATCH = "order_total_mismatch"
    MISSING_PAID_AT = "missing_paid_at"
    MISSING_SHIPPED_AT = "missing_shipped_at"
    MISSING_DELIVERED_AT = "missing_delivered_at"
    MISSING_RECEIVED_AT = "missing_received_at"
    MISSING_RETURN_CURRENCY = "missing_return_currency"
    MISSING_REFUNDED_AT = "missing_refunded_at"


@dataclass(frozen=True, slots=True)
class CsvIntegrityIssue:
    """Describe one row-level integrity problem without retaining cell values."""

    code: CsvIntegrityErrorCode
    filename: str
    row_number: int
    columns: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class CsvIntegrityValidationResult:
    """Summarize deterministic row-level integrity validation."""

    schema: CsvSchema
    row_count: int
    issues: tuple[CsvIntegrityIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Return whether every row passed all applicable integrity rules."""

        return not self.issues

    @property
    def issue_count(self) -> int:
        """Return the number of integrity issues."""

        return len(self.issues)

    @property
    def invalid_row_numbers(self) -> frozenset[int]:
        """Return positional data-row numbers containing integrity issues."""

        return frozenset(issue.row_number for issue in self.issues)

    @property
    def invalid_row_count(self) -> int:
        """Return the number of rows containing at least one issue."""

        return len(self.invalid_row_numbers)

    @property
    def valid_row_count(self) -> int:
        """Return the number of rows without integrity issues."""

        return self.row_count - self.invalid_row_count


def _issue(
    code: CsvIntegrityErrorCode,
    schema: CsvSchema,
    row_number: int,
    columns: tuple[str, ...],
    explanation: str,
) -> CsvIntegrityIssue:
    return CsvIntegrityIssue(
        code=code,
        filename=schema.filename,
        row_number=row_number,
        columns=columns,
        message=(
            f"CSV file {schema.filename!r}, data row {row_number}, "
            f"column(s) {', '.join(repr(column) for column in columns)}: "
            f"{explanation}"
        ),
    )


def _is_missing(row: Mapping[str, str], column: str) -> bool:
    if column not in row:
        return True
    return not row[column].strip()


def _value(row: Mapping[str, str], column: str) -> str:
    return row[column]


def _order_id_issue(
    row: Mapping[str, str],
    schema: CsvSchema,
    row_number: int,
) -> CsvIntegrityIssue | None:
    order_id = _value(row, "order_id")
    platform = _value(row, "platform")
    source_order_id = _value(row, "source_order_id")
    if order_id == f"{platform}:{source_order_id}":
        return None

    return _issue(
        CsvIntegrityErrorCode.ORDER_ID_MISMATCH,
        schema,
        row_number,
        ("order_id", "platform", "source_order_id"),
        (
            "the deterministic order identifier does not match its source fields. "
            "Use the exact platform:source_order_id format."
        ),
    )


def _order_total_issue(
    row: Mapping[str, str],
    schema: CsvSchema,
    row_number: int,
) -> CsvIntegrityIssue | None:
    subtotal = Decimal(_value(row, "subtotal"))
    discount_total = Decimal(_value(row, "discount_total"))
    shipping_total = Decimal(_value(row, "shipping_total"))
    tax_total = Decimal(_value(row, "tax_total"))
    order_total = Decimal(_value(row, "order_total"))
    calculated_total = subtotal - discount_total + shipping_total + tax_total

    if abs(calculated_total - order_total) <= DEFAULT_MONETARY_TOLERANCE:
        return None

    return _issue(
        CsvIntegrityErrorCode.ORDER_TOTAL_MISMATCH,
        schema,
        row_number,
        (
            "subtotal",
            "discount_total",
            "shipping_total",
            "tax_total",
            "order_total",
        ),
        (
            "the order total does not match the documented formula within the "
            "permitted monetary tolerance. Correct the component totals or final total."
        ),
    )


def _payment_issues(
    row: Mapping[str, str],
    schema: CsvSchema,
    row_number: int,
) -> tuple[CsvIntegrityIssue, ...]:
    if _value(row, "payment_status") != "succeeded":
        return ()
    if not _is_missing(row, "paid_at"):
        return ()
    return (
        _issue(
            CsvIntegrityErrorCode.MISSING_PAID_AT,
            schema,
            row_number,
            ("payment_status", "paid_at"),
            "a succeeded payment requires paid_at. Provide its ISO 8601 date-time.",
        ),
    )


def _shipment_issues(
    row: Mapping[str, str],
    schema: CsvSchema,
    row_number: int,
) -> tuple[CsvIntegrityIssue, ...]:
    shipment_status = _value(row, "shipment_status")
    if shipment_status not in {"shipped", "delivered"}:
        return ()

    issues: list[CsvIntegrityIssue] = []
    if _is_missing(row, "shipped_at"):
        issues.append(
            _issue(
                CsvIntegrityErrorCode.MISSING_SHIPPED_AT,
                schema,
                row_number,
                ("shipment_status", "shipped_at"),
                "a shipped or delivered shipment requires shipped_at.",
            )
        )
    if shipment_status == "delivered" and _is_missing(row, "delivered_at"):
        issues.append(
            _issue(
                CsvIntegrityErrorCode.MISSING_DELIVERED_AT,
                schema,
                row_number,
                ("shipment_status", "delivered_at"),
                "a delivered shipment requires delivered_at.",
            )
        )
    return tuple(issues)


def _return_issues(
    row: Mapping[str, str],
    schema: CsvSchema,
    row_number: int,
) -> tuple[CsvIntegrityIssue, ...]:
    issues: list[CsvIntegrityIssue] = []
    return_status = _value(row, "return_status")
    if return_status in {"received", "completed"} and _is_missing(row, "received_at"):
        issues.append(
            _issue(
                CsvIntegrityErrorCode.MISSING_RECEIVED_AT,
                schema,
                row_number,
                ("return_status", "received_at"),
                "a received or completed return requires received_at.",
            )
        )

    if not _is_missing(row, "expected_refund_amount") and _is_missing(row, "currency"):
        issues.append(
            _issue(
                CsvIntegrityErrorCode.MISSING_RETURN_CURRENCY,
                schema,
                row_number,
                ("expected_refund_amount", "currency"),
                "an expected refund amount requires its currency.",
            )
        )

    return tuple(issues)


def _refund_issues(
    row: Mapping[str, str],
    schema: CsvSchema,
    row_number: int,
) -> tuple[CsvIntegrityIssue, ...]:
    if _value(row, "refund_status") != "succeeded":
        return ()
    if not _is_missing(row, "refunded_at"):
        return ()
    return (
        _issue(
            CsvIntegrityErrorCode.MISSING_REFUNDED_AT,
            schema,
            row_number,
            ("refund_status", "refunded_at"),
            "a succeeded refund requires refunded_at. Provide its ISO 8601 date-time.",
        ),
    )


def _validate_preconditions(
    dataframe: pd.DataFrame,
    schema: CsvSchema,
    value_result: CsvValueValidationResult,
) -> None:
    prerequisite_message = (
        "Value validation must complete successfully before integrity validation."
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


def validate_csv_integrity(
    dataframe: pd.DataFrame,
    schema: CsvSchema,
    value_result: CsvValueValidationResult,
) -> CsvIntegrityValidationResult:
    """Validate row integrity after successful cell-value validation."""

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError(
            "dataframe must be a pandas DataFrame. Value validation must complete "
            "successfully before integrity validation."
        )
    if not isinstance(value_result, CsvValueValidationResult):
        raise TypeError(
            "value_result must be a CsvValueValidationResult. Value validation "
            "must complete successfully before integrity validation."
        )

    _validate_preconditions(dataframe, schema, value_result)

    issues: list[CsvIntegrityIssue] = []
    column_names = tuple(str(column) for column in dataframe.columns)
    for row_number, values in enumerate(
        dataframe.itertuples(index=False, name=None),
        start=1,
    ):
        row = dict(zip(column_names, values, strict=True))

        order_id_issue = _order_id_issue(row, schema, row_number)
        if order_id_issue is not None:
            issues.append(order_id_issue)

        if schema.filename == "orders.csv":
            order_total_issue = _order_total_issue(row, schema, row_number)
            if order_total_issue is not None:
                issues.append(order_total_issue)
        elif schema.filename == "payments.csv":
            issues.extend(_payment_issues(row, schema, row_number))
        elif schema.filename == "shipments.csv":
            issues.extend(_shipment_issues(row, schema, row_number))
        elif schema.filename == "returns.csv":
            issues.extend(_return_issues(row, schema, row_number))
        elif schema.filename == "refunds.csv":
            issues.extend(_refund_issues(row, schema, row_number))

    return CsvIntegrityValidationResult(
        schema=schema,
        row_count=len(dataframe),
        issues=tuple(issues),
    )
