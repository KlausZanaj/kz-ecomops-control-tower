"""Tests for row-level integrity validation of normalized CSV data."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pandas as pd
import pytest

from kz_ecomops.validation import (
    CSV_SCHEMAS,
    DEFAULT_MONETARY_TOLERANCE,
    CsvIntegrityErrorCode,
    CsvIntegrityIssue,
    CsvIntegrityValidationResult,
    CsvValueValidationResult,
    validate_csv_integrity,
    validate_csv_values,
)


VALID_INTEGRITY_ROWS = {
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
        "paid_at": "2026-08-14T10:31:00+02:00",
        "created_at": "2026-08-14T10:31:00+02:00",
        "updated_at": "2026-08-14T10:31:00+02:00",
    },
    "shipments.csv": {
        "shipment_id": "shipment-001",
        "platform": "shopify",
        "order_id": "shopify:001",
        "source_order_id": "001",
        "shipment_status": "delivered",
        "tracking_number": "tracking-001",
        "shipped_at": "2026-08-15T09:00:00+02:00",
        "delivered_at": "2026-08-16T09:00:00+02:00",
        "updated_at": "2026-08-16T09:00:00+02:00",
    },
    "returns.csv": {
        "return_id": "return-001",
        "platform": "shopify",
        "order_id": "shopify:001",
        "source_order_id": "001",
        "return_status": "received",
        "requested_at": "2026-08-20T09:00:00+02:00",
        "received_at": "2026-08-22T09:00:00+02:00",
        "expected_refund_amount": "14.20",
        "currency": "EUR",
        "updated_at": "2026-08-22T09:00:00+02:00",
    },
    "refunds.csv": {
        "refund_id": "refund-001",
        "platform": "shopify",
        "order_id": "shopify:001",
        "source_order_id": "001",
        "refund_status": "succeeded",
        "amount": "14.20",
        "currency": "EUR",
        "refunded_at": "2026-08-23T09:00:00+02:00",
        "created_at": "2026-08-23T09:00:00+02:00",
        "updated_at": "2026-08-23T09:00:00+02:00",
    },
}


def _validated_dataframe(
    filename: str,
    *,
    changes: dict[str, str] | None = None,
    omitted: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, CsvValueValidationResult]:
    row = dict(VALID_INTEGRITY_ROWS[filename])
    if changes:
        row.update(changes)
    for column in omitted:
        row.pop(column, None)
    dataframe = pd.DataFrame([row])
    value_result = validate_csv_values(dataframe, CSV_SCHEMAS[filename])
    assert value_result.is_valid
    return dataframe, value_result


def _validate_integrity(
    filename: str,
    *,
    changes: dict[str, str] | None = None,
    omitted: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, CsvIntegrityValidationResult]:
    dataframe, value_result = _validated_dataframe(
        filename,
        changes=changes,
        omitted=omitted,
    )
    result = validate_csv_integrity(
        dataframe,
        CSV_SCHEMAS[filename],
        value_result,
    )
    return dataframe, result


def _only_issue(result: CsvIntegrityValidationResult) -> CsvIntegrityIssue:
    assert result.issue_count == 1
    return result.issues[0]


@pytest.mark.parametrize("filename", tuple(VALID_INTEGRITY_ROWS))
def test_accepts_integral_record_for_each_required_csv(filename: str) -> None:
    _, result = _validate_integrity(filename)

    assert result.is_valid
    assert result.row_count == 1
    assert result.valid_row_count == 1


def test_accepts_dataframe_with_zero_rows() -> None:
    schema = CSV_SCHEMAS["orders.csv"]
    dataframe = pd.DataFrame(columns=schema.column_names)
    value_result = validate_csv_values(dataframe, schema)

    result = validate_csv_integrity(dataframe, schema, value_result)

    assert result.is_valid
    assert result.row_count == 0
    assert result.valid_row_count == 0
    assert result.invalid_row_count == 0


@pytest.mark.parametrize("filename", tuple(VALID_INTEGRITY_ROWS))
def test_accepts_exact_deterministic_order_id_for_each_csv(filename: str) -> None:
    _, result = _validate_integrity(filename)

    assert all(
        issue.code is not CsvIntegrityErrorCode.ORDER_ID_MISMATCH
        for issue in result.issues
    )


@pytest.mark.parametrize("filename", tuple(VALID_INTEGRITY_ROWS))
def test_reports_wrong_deterministic_order_id_for_each_csv(filename: str) -> None:
    _, result = _validate_integrity(filename, changes={"order_id": "wrong-id"})

    issue = _only_issue(result)
    assert issue.code is CsvIntegrityErrorCode.ORDER_ID_MISMATCH
    assert issue.columns == ("order_id", "platform", "source_order_id")


def test_does_not_correct_order_id_automatically() -> None:
    dataframe, result = _validate_integrity(
        "orders.csv", changes={"order_id": "wrong-id"}
    )

    assert not result.is_valid
    assert dataframe.at[0, "order_id"] == "wrong-id"


def test_accepts_exact_order_total_formula() -> None:
    _, result = _validate_integrity("orders.csv")

    assert result.is_valid


def test_accepts_order_total_difference_equal_to_tolerance() -> None:
    _, result = _validate_integrity(
        "orders.csv", changes={"order_total": "14.21"}
    )

    assert result.is_valid


def test_rejects_order_total_difference_above_tolerance() -> None:
    _, result = _validate_integrity(
        "orders.csv", changes={"order_total": "14.22"}
    )

    issue = _only_issue(result)
    assert issue.code is CsvIntegrityErrorCode.ORDER_TOTAL_MISMATCH
    assert issue.columns == (
        "subtotal",
        "discount_total",
        "shipping_total",
        "tax_total",
        "order_total",
    )


def test_order_total_uses_decimal_precision_instead_of_float() -> None:
    _, result = _validate_integrity(
        "orders.csv",
        changes={
            "subtotal": "9007199254740992.00",
            "discount_total": "0.00",
            "shipping_total": "0.01",
            "tax_total": "0.00",
            "order_total": "9007199254740992.03",
        },
    )

    issue = _only_issue(result)
    assert issue.code is CsvIntegrityErrorCode.ORDER_TOTAL_MISMATCH


def test_accepts_succeeded_payment_with_paid_at() -> None:
    _, result = _validate_integrity("payments.csv")

    assert result.is_valid


def test_reports_succeeded_payment_without_paid_at_column() -> None:
    _, result = _validate_integrity("payments.csv", omitted=("paid_at",))

    issue = _only_issue(result)
    assert issue.code is CsvIntegrityErrorCode.MISSING_PAID_AT
    assert issue.columns == ("payment_status", "paid_at")


@pytest.mark.parametrize("status", ["pending", "failed", "cancelled", "reversed"])
def test_does_not_require_paid_at_for_other_payment_statuses(status: str) -> None:
    _, result = _validate_integrity(
        "payments.csv",
        changes={"payment_status": status},
        omitted=("paid_at",),
    )

    assert result.is_valid


def test_accepts_complete_shipped_shipment() -> None:
    _, result = _validate_integrity(
        "shipments.csv",
        changes={"shipment_status": "shipped"},
        omitted=("delivered_at",),
    )

    assert result.is_valid


def test_reports_shipped_shipment_without_tracking() -> None:
    _, result = _validate_integrity(
        "shipments.csv",
        changes={"shipment_status": "shipped"},
        omitted=("tracking_number", "delivered_at"),
    )

    issue = _only_issue(result)
    assert issue.code is CsvIntegrityErrorCode.MISSING_TRACKING_NUMBER


def test_reports_shipped_shipment_without_shipped_at() -> None:
    _, result = _validate_integrity(
        "shipments.csv",
        changes={"shipment_status": "shipped"},
        omitted=("shipped_at", "delivered_at"),
    )

    issue = _only_issue(result)
    assert issue.code is CsvIntegrityErrorCode.MISSING_SHIPPED_AT


def test_accepts_complete_delivered_shipment() -> None:
    _, result = _validate_integrity("shipments.csv")

    assert result.is_valid


def test_delivered_shipment_reports_three_missing_fields_in_order() -> None:
    _, result = _validate_integrity(
        "shipments.csv",
        omitted=("tracking_number", "shipped_at", "delivered_at"),
    )

    assert [issue.code for issue in result.issues] == [
        CsvIntegrityErrorCode.MISSING_TRACKING_NUMBER,
        CsvIntegrityErrorCode.MISSING_SHIPPED_AT,
        CsvIntegrityErrorCode.MISSING_DELIVERED_AT,
    ]


@pytest.mark.parametrize(
    "status", ["pending", "ready", "failed", "cancelled", "returned"]
)
def test_does_not_require_shipping_fields_for_other_statuses(status: str) -> None:
    _, result = _validate_integrity(
        "shipments.csv",
        changes={"shipment_status": status},
        omitted=("tracking_number", "shipped_at", "delivered_at"),
    )

    assert result.is_valid


@pytest.mark.parametrize("status", ["received", "completed"])
def test_accepts_received_or_completed_return_with_received_at(status: str) -> None:
    _, result = _validate_integrity(
        "returns.csv", changes={"return_status": status}
    )

    assert result.is_valid


@pytest.mark.parametrize("status", ["received", "completed"])
def test_reports_received_or_completed_return_without_received_at(
    status: str,
) -> None:
    _, result = _validate_integrity(
        "returns.csv",
        changes={"return_status": status},
        omitted=("received_at",),
    )

    issue = _only_issue(result)
    assert issue.code is CsvIntegrityErrorCode.MISSING_RECEIVED_AT


@pytest.mark.parametrize(
    "status", ["requested", "approved", "in_transit", "rejected", "cancelled"]
)
def test_does_not_require_received_at_for_other_return_statuses(status: str) -> None:
    _, result = _validate_integrity(
        "returns.csv",
        changes={"return_status": status},
        omitted=("received_at",),
    )

    assert result.is_valid


def test_accepts_expected_refund_amount_with_currency() -> None:
    _, result = _validate_integrity("returns.csv")

    assert result.is_valid


def test_reports_expected_refund_amount_without_currency() -> None:
    _, result = _validate_integrity("returns.csv", omitted=("currency",))

    issue = _only_issue(result)
    assert issue.code is CsvIntegrityErrorCode.MISSING_RETURN_CURRENCY
    assert issue.columns == ("expected_refund_amount", "currency")


def test_accepts_currency_without_expected_refund_amount() -> None:
    _, result = _validate_integrity(
        "returns.csv", omitted=("expected_refund_amount",)
    )

    assert result.is_valid


def test_accepts_succeeded_refund_with_refunded_at() -> None:
    _, result = _validate_integrity("refunds.csv")

    assert result.is_valid


def test_reports_succeeded_refund_without_refunded_at() -> None:
    _, result = _validate_integrity("refunds.csv", omitted=("refunded_at",))

    issue = _only_issue(result)
    assert issue.code is CsvIntegrityErrorCode.MISSING_REFUNDED_AT


@pytest.mark.parametrize("status", ["pending", "failed", "cancelled"])
def test_does_not_require_refunded_at_for_other_refund_statuses(status: str) -> None:
    _, result = _validate_integrity(
        "refunds.csv",
        changes={"refund_status": status},
        omitted=("refunded_at",),
    )

    assert result.is_valid


def test_does_not_require_cancelled_at_for_cancelled_order() -> None:
    _, result = _validate_integrity(
        "orders.csv",
        changes={"order_status": "cancelled"},
        omitted=("cancelled_at",),
    )

    assert result.is_valid


def test_treats_whitespace_only_conditional_field_as_missing() -> None:
    _, result = _validate_integrity(
        "shipments.csv", changes={"tracking_number": "   "}
    )

    issue = _only_issue(result)
    assert issue.code is CsvIntegrityErrorCode.MISSING_TRACKING_NUMBER


def test_issues_follow_row_then_rule_order() -> None:
    first_row = dict(VALID_INTEGRITY_ROWS["shipments.csv"])
    first_row.update(
        order_id="wrong-id",
        tracking_number="",
        shipped_at="",
        delivered_at="",
    )
    second_row = dict(VALID_INTEGRITY_ROWS["shipments.csv"])
    second_row["tracking_number"] = ""
    dataframe = pd.DataFrame([first_row, second_row])
    value_result = validate_csv_values(dataframe, CSV_SCHEMAS["shipments.csv"])
    assert value_result.is_valid

    result = validate_csv_integrity(
        dataframe, CSV_SCHEMAS["shipments.csv"], value_result
    )

    assert [(issue.row_number, issue.code) for issue in result.issues] == [
        (1, CsvIntegrityErrorCode.ORDER_ID_MISMATCH),
        (1, CsvIntegrityErrorCode.MISSING_TRACKING_NUMBER),
        (1, CsvIntegrityErrorCode.MISSING_SHIPPED_AT),
        (1, CsvIntegrityErrorCode.MISSING_DELIVERED_AT),
        (2, CsvIntegrityErrorCode.MISSING_TRACKING_NUMBER),
    ]


def test_valid_and_invalid_row_counts() -> None:
    valid_row = dict(VALID_INTEGRITY_ROWS["orders.csv"])
    invalid_row = dict(valid_row)
    invalid_row["order_id"] = "wrong-id"
    dataframe = pd.DataFrame([valid_row, invalid_row])
    value_result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
    assert value_result.is_valid

    result = validate_csv_integrity(
        dataframe, CSV_SCHEMAS["orders.csv"], value_result
    )

    assert result.row_count == 2
    assert result.invalid_row_numbers == frozenset({2})
    assert result.invalid_row_count == 1
    assert result.valid_row_count == 1


def test_csv_integrity_issue_is_frozen_and_slotted() -> None:
    issue = CsvIntegrityIssue(
        code=CsvIntegrityErrorCode.ORDER_ID_MISMATCH,
        filename="orders.csv",
        row_number=1,
        columns=("order_id", "platform", "source_order_id"),
        message="Correct the deterministic identifier.",
    )

    with pytest.raises(FrozenInstanceError):
        issue.row_number = 2  # type: ignore[misc]
    assert not hasattr(issue, "__dict__")


def test_csv_integrity_result_is_frozen_and_slotted() -> None:
    result = CsvIntegrityValidationResult(
        schema=CSV_SCHEMAS["orders.csv"],
        row_count=0,
    )

    with pytest.raises(FrozenInstanceError):
        result.row_count = 1  # type: ignore[misc]
    assert not hasattr(result, "__dict__")


def test_integrity_error_code_values_are_exact() -> None:
    assert {code.value for code in CsvIntegrityErrorCode} == {
        "order_id_mismatch",
        "order_total_mismatch",
        "missing_paid_at",
        "missing_tracking_number",
        "missing_shipped_at",
        "missing_delivered_at",
        "missing_received_at",
        "missing_return_currency",
        "missing_refunded_at",
    }


def test_default_monetary_tolerance_is_exact_decimal() -> None:
    assert isinstance(DEFAULT_MONETARY_TOLERANCE, Decimal)
    assert DEFAULT_MONETARY_TOLERANCE == Decimal("0.01")


def test_integrity_validation_does_not_modify_dataframe() -> None:
    dataframe, value_result = _validated_dataframe(
        "orders.csv", changes={"order_id": "wrong-id", "order_total": "14.22"}
    )
    original = dataframe.copy(deep=True)

    validate_csv_integrity(dataframe, CSV_SCHEMAS["orders.csv"], value_result)

    pd.testing.assert_frame_equal(dataframe, original)


def test_integrity_message_does_not_expose_original_values() -> None:
    private_value = "PRIVATE-ORDER-ID"
    _, result = _validate_integrity(
        "orders.csv", changes={"order_id": private_value}
    )

    issue = _only_issue(result)
    assert private_value not in issue.message
    assert "orders.csv" in issue.message
    assert "data row 1" in issue.message


def test_ignores_additional_columns() -> None:
    _, result = _validate_integrity(
        "orders.csv", changes={"external_metadata": "ignored"}
    )

    assert result.is_valid


def test_rejects_non_dataframe_input() -> None:
    dataframe, value_result = _validated_dataframe("orders.csv")

    with pytest.raises(TypeError, match="pandas DataFrame"):
        validate_csv_integrity(
            [],  # type: ignore[arg-type]
            CSV_SCHEMAS["orders.csv"],
            value_result,
        )
    assert isinstance(dataframe, pd.DataFrame)


def test_rejects_wrong_value_result_type() -> None:
    dataframe, _ = _validated_dataframe("orders.csv")

    with pytest.raises(TypeError, match="CsvValueValidationResult"):
        validate_csv_integrity(
            dataframe,
            CSV_SCHEMAS["orders.csv"],
            None,  # type: ignore[arg-type]
        )


def test_rejects_value_result_for_different_schema() -> None:
    dataframe, value_result = _validated_dataframe("orders.csv")

    with pytest.raises(
        ValueError,
        match="Value validation must complete successfully before integrity validation",
    ):
        validate_csv_integrity(
            dataframe,
            CSV_SCHEMAS["payments.csv"],
            value_result,
        )


def test_rejects_value_result_with_different_row_count() -> None:
    dataframe, value_result = _validated_dataframe("orders.csv")
    two_rows = pd.concat([dataframe, dataframe], ignore_index=True)

    with pytest.raises(
        ValueError,
        match="Value validation must complete successfully before integrity validation",
    ):
        validate_csv_integrity(
            two_rows,
            CSV_SCHEMAS["orders.csv"],
            value_result,
        )


def test_rejects_value_result_containing_issues() -> None:
    invalid_dataframe = pd.DataFrame(
        [dict(VALID_INTEGRITY_ROWS["orders.csv"], platform="invalid")]
    )
    value_result = validate_csv_values(
        invalid_dataframe, CSV_SCHEMAS["orders.csv"]
    )
    assert not value_result.is_valid

    with pytest.raises(
        ValueError,
        match="Value validation must complete successfully before integrity validation",
    ):
        validate_csv_integrity(
            invalid_dataframe,
            CSV_SCHEMAS["orders.csv"],
            value_result,
        )
