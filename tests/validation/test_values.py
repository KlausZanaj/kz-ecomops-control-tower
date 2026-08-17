"""Tests for cell-level validation of structurally valid CSV data."""

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from kz_ecomops.validation import (
    CSV_SCHEMAS,
    CsvValueErrorCode,
    CsvValueIssue,
    CsvValueValidationResult,
    validate_csv_values,
)


VALID_ROWS = {
    "orders.csv": {
        "order_id": "shopify:001",
        "platform": "shopify",
        "source_order_id": "001",
        "ordered_at": "2026-08-14T10:30:00+02:00",
        "order_status": "pending",
        "payment_status": "pending",
        "fulfillment_status": "unfulfilled",
        "currency": "EUR",
        "subtotal": "10.00",
        "discount_total": "0.00",
        "shipping_total": "2.00",
        "tax_total": "2.20",
        "order_total": "14.20",
        "updated_at": "2026-08-14T10:30:00+02:00",
    },
    "payments.csv": {
        "payment_id": "payment-001",
        "platform": "shopify",
        "order_id": "shopify:001",
        "source_order_id": "001",
        "payment_status": "succeeded",
        "amount": "14.20",
        "currency": "EUR",
        "created_at": "2026-08-14T10:31:00+02:00",
        "updated_at": "2026-08-14T10:31:00+02:00",
    },
    "shipments.csv": {
        "shipment_id": "shipment-001",
        "platform": "shopify",
        "order_id": "shopify:001",
        "source_order_id": "001",
        "shipment_status": "pending",
        "updated_at": "2026-08-14T11:00:00+02:00",
    },
    "returns.csv": {
        "return_id": "return-001",
        "platform": "shopify",
        "order_id": "shopify:001",
        "source_order_id": "001",
        "return_status": "requested",
        "requested_at": "2026-08-20T09:00:00+02:00",
        "updated_at": "2026-08-20T09:00:00+02:00",
    },
    "refunds.csv": {
        "refund_id": "refund-001",
        "platform": "shopify",
        "order_id": "shopify:001",
        "source_order_id": "001",
        "refund_status": "succeeded",
        "amount": "14.20",
        "currency": "EUR",
        "created_at": "2026-08-21T09:00:00+02:00",
        "updated_at": "2026-08-21T09:00:00+02:00",
    },
}

ALLOWED_VALUE_COLUMNS = [
    (filename, column.name)
    for filename, schema in CSV_SCHEMAS.items()
    for column in schema.columns
    if column.allowed_values is not None
]


def _dataframe(filename: str, **changes: object) -> pd.DataFrame:
    row: dict[str, object] = dict(VALID_ROWS[filename])
    row.update(changes)
    return pd.DataFrame([row])


def _only_issue(result: CsvValueValidationResult) -> CsvValueIssue:
    assert result.issue_count == 1
    return result.issues[0]


@pytest.mark.parametrize("filename", tuple(VALID_ROWS))
def test_accepts_minimal_valid_row_for_each_required_schema(filename: str) -> None:
    result = validate_csv_values(_dataframe(filename), CSV_SCHEMAS[filename])

    assert result.is_valid
    assert result.issue_count == 0
    assert result.row_count == 1
    assert result.valid_row_count == 1


def test_accepts_valid_dataframe_with_zero_rows() -> None:
    schema = CSV_SCHEMAS["orders.csv"]
    dataframe = pd.DataFrame(columns=schema.column_names)

    result = validate_csv_values(dataframe, schema)

    assert result.is_valid
    assert result.row_count == 0
    assert result.valid_row_count == 0
    assert result.invalid_row_count == 0


def test_accepts_absent_optional_columns() -> None:
    dataframe = _dataframe("payments.csv")

    result = validate_csv_values(dataframe, CSV_SCHEMAS["payments.csv"])

    assert result.is_valid
    assert "provider_transaction_id" not in dataframe.columns


def test_ignores_additional_columns_even_with_non_string_values() -> None:
    dataframe = _dataframe("orders.csv", external_metadata=object())

    result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    assert result.is_valid


@pytest.mark.parametrize("missing_value", ["", "   "])
def test_reports_empty_required_value(missing_value: str) -> None:
    dataframe = _dataframe("orders.csv", order_id=missing_value)

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
    )

    assert issue.code is CsvValueErrorCode.MISSING_REQUIRED_VALUE
    assert issue.row_number == 1
    assert issue.column == "order_id"


@pytest.mark.parametrize("empty_value", ["", "   "])
def test_accepts_empty_optional_value(empty_value: str) -> None:
    dataframe = _dataframe("payments.csv", paid_at=empty_value)

    result = validate_csv_values(dataframe, CSV_SCHEMAS["payments.csv"])

    assert result.is_valid


@pytest.mark.parametrize("marker", ["N/A", "n/a", "NULL", " null ", "-"])
def test_reports_disallowed_missing_markers(marker: str) -> None:
    dataframe = _dataframe("orders.csv", order_id=marker)

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
    )

    assert issue.code is CsvValueErrorCode.DISALLOWED_MISSING_MARKER


@pytest.mark.parametrize("value", [42, None, float("nan"), pd.NA])
def test_reports_non_string_values(value: object) -> None:
    dataframe = _dataframe("orders.csv", platform=value)

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
    )

    assert issue.code is CsvValueErrorCode.NON_STRING_VALUE
    assert issue.column == "platform"


@pytest.mark.parametrize("filename,column_name", ALLOWED_VALUE_COLUMNS)
def test_applies_every_allowed_value_set(filename: str, column_name: str) -> None:
    dataframe = _dataframe(filename, **{column_name: "not-a-documented-value"})

    issue = _only_issue(validate_csv_values(dataframe, CSV_SCHEMAS[filename]))

    assert issue.code is CsvValueErrorCode.INVALID_ALLOWED_VALUE
    assert issue.column == column_name


def test_allowed_value_comparison_is_case_sensitive() -> None:
    dataframe = _dataframe("orders.csv", platform="Shopify")

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
    )

    assert issue.code is CsvValueErrorCode.INVALID_ALLOWED_VALUE


@pytest.mark.parametrize("value", ["0.00", "12.34", "0001.50", "-1.25"])
def test_accepts_plain_decimals_with_exactly_two_places(value: str) -> None:
    dataframe = _dataframe("returns.csv", expected_refund_amount=value)

    result = validate_csv_values(dataframe, CSV_SCHEMAS["returns.csv"])

    assert result.is_valid


@pytest.mark.parametrize(
    "value",
    ["not-numeric", "1,00", "1e2", "NaN", "Infinity", "-Infinity", " 1.00"],
)
def test_rejects_unsupported_decimal_representations(value: str) -> None:
    dataframe = _dataframe("returns.csv", expected_refund_amount=value)

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["returns.csv"])
    )

    assert issue.code is CsvValueErrorCode.INVALID_DECIMAL


@pytest.mark.parametrize("value", ["1.0", "1.000"])
def test_rejects_wrong_number_of_decimal_places(value: str) -> None:
    dataframe = _dataframe("returns.csv", expected_refund_amount=value)

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["returns.csv"])
    )

    assert issue.code is CsvValueErrorCode.INVALID_DECIMAL


def test_accepts_inclusive_minimum() -> None:
    dataframe = _dataframe("orders.csv", subtotal="0.00")

    result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    assert result.is_valid


def test_reports_value_below_inclusive_minimum() -> None:
    dataframe = _dataframe("orders.csv", subtotal="-0.01")

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
    )

    assert issue.code is CsvValueErrorCode.MINIMUM_VIOLATION
    assert issue.column == "subtotal"


def test_applies_exclusive_minimum_to_payment_amount() -> None:
    dataframe = _dataframe("payments.csv", amount="0.00")

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["payments.csv"])
    )

    assert issue.code is CsvValueErrorCode.MINIMUM_VIOLATION
    assert issue.column == "amount"


def test_applies_exclusive_minimum_to_refund_amount() -> None:
    dataframe = _dataframe("refunds.csv", amount="0.00")

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["refunds.csv"])
    )

    assert issue.code is CsvValueErrorCode.MINIMUM_VIOLATION
    assert issue.column == "amount"


def test_does_not_invent_minimum_for_expected_return_amount() -> None:
    dataframe = _dataframe("returns.csv", expected_refund_amount="-100.00")

    result = validate_csv_values(dataframe, CSV_SCHEMAS["returns.csv"])

    assert result.is_valid


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-14T10:30:00+02:00",
        "2026-08-14T08:30:00Z",
        "2026-08-14T10:30:00.123456+02:00",
    ],
)
def test_accepts_supported_iso_datetimes(value: str) -> None:
    dataframe = _dataframe("orders.csv", ordered_at=value)

    result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    assert result.is_valid


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-14T10:30:00",
        "2026-08-14 10:30:00+02:00",
        "2026-02-30T10:30:00+02:00",
        "2026-08-14T25:30:00+02:00",
        "2026-08-14T10:30:00+24:00",
        "2026-08-14T10:30:00+02:60",
    ],
)
def test_rejects_unsupported_or_impossible_datetimes(value: str) -> None:
    dataframe = _dataframe("orders.csv", ordered_at=value)

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
    )

    assert issue.code is CsvValueErrorCode.INVALID_DATETIME


def test_multiple_issues_on_one_row_count_as_one_invalid_row() -> None:
    dataframe = _dataframe(
        "orders.csv",
        platform="invalid",
        currency="invalid",
        subtotal="invalid",
    )

    result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    assert result.issue_count == 3
    assert result.invalid_row_numbers == frozenset({1})
    assert result.invalid_row_count == 1
    assert result.valid_row_count == 0


def test_issues_follow_row_then_schema_column_order() -> None:
    first_row = dict(VALID_ROWS["orders.csv"])
    first_row.update(order_id="", platform="invalid")
    second_row = dict(VALID_ROWS["orders.csv"])
    second_row.update(order_status="invalid", updated_at="invalid")
    dataframe = pd.DataFrame([first_row, second_row])
    dataframe = dataframe[list(reversed(dataframe.columns))]

    result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    assert [(issue.row_number, issue.column) for issue in result.issues] == [
        (1, "order_id"),
        (1, "platform"),
        (2, "order_status"),
        (2, "updated_at"),
    ]


def test_valid_and_invalid_row_counts() -> None:
    valid_row = dict(VALID_ROWS["orders.csv"])
    invalid_row = dict(valid_row)
    invalid_row["currency"] = "invalid"
    dataframe = pd.DataFrame([valid_row, invalid_row])

    result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    assert result.row_count == 2
    assert result.invalid_row_numbers == frozenset({2})
    assert result.invalid_row_count == 1
    assert result.valid_row_count == 1
    assert not result.is_valid


def test_row_numbers_are_positional_and_ignore_dataframe_index() -> None:
    dataframe = _dataframe("orders.csv", currency="invalid")
    dataframe.index = [99]

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
    )

    assert issue.row_number == 1


def test_each_cell_produces_at_most_one_issue() -> None:
    dataframe = _dataframe("orders.csv", currency=None)

    result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    assert result.issue_count == 1
    assert result.issues[0].code is CsvValueErrorCode.NON_STRING_VALUE


def test_issue_message_is_useful_without_exposing_original_value() -> None:
    secret_value = "PRIVATE-SOURCE-VALUE"
    dataframe = _dataframe("orders.csv", platform=secret_value)

    issue = _only_issue(
        validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
    )

    assert secret_value not in issue.message
    assert "orders.csv" in issue.message
    assert "data row 1" in issue.message
    assert "platform" in issue.message


def test_csv_value_issue_is_frozen_and_slotted() -> None:
    issue = CsvValueIssue(
        code=CsvValueErrorCode.INVALID_DECIMAL,
        filename="orders.csv",
        row_number=1,
        column="subtotal",
        message="Correct the decimal format.",
    )

    with pytest.raises(FrozenInstanceError):
        issue.column = "changed"  # type: ignore[misc]
    assert not hasattr(issue, "__dict__")


def test_csv_value_validation_result_is_frozen_and_slotted() -> None:
    result = CsvValueValidationResult(
        schema=CSV_SCHEMAS["orders.csv"],
        row_count=0,
    )

    with pytest.raises(FrozenInstanceError):
        result.row_count = 1  # type: ignore[misc]
    assert not hasattr(result, "__dict__")


def test_csv_value_error_code_values_are_exact() -> None:
    assert {code.value for code in CsvValueErrorCode} == {
        "missing_required_value",
        "disallowed_missing_marker",
        "non_string_value",
        "invalid_allowed_value",
        "invalid_decimal",
        "minimum_violation",
        "invalid_datetime",
    }


def test_validation_does_not_modify_dataframe() -> None:
    dataframe = _dataframe(
        "orders.csv",
        platform="invalid",
        subtotal="-0.01",
        external="unchanged",
    )
    original = dataframe.copy(deep=True)

    validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    pd.testing.assert_frame_equal(dataframe, original)


def test_rejects_non_dataframe_input() -> None:
    with pytest.raises(TypeError, match="pandas DataFrame"):
        validate_csv_values([], CSV_SCHEMAS["orders.csv"])  # type: ignore[arg-type]


def test_rejects_structurally_missing_required_column() -> None:
    dataframe = _dataframe("orders.csv").drop(columns="order_id")

    with pytest.raises(
        ValueError,
        match="Run structural CSV validation before value validation",
    ):
        validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])


def test_rejects_duplicate_dataframe_column_names() -> None:
    dataframe = _dataframe("orders.csv")
    dataframe.columns = [
        "platform" if column == "order_id" else column
        for column in dataframe.columns
    ]

    with pytest.raises(ValueError, match="duplicate column names"):
        validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
