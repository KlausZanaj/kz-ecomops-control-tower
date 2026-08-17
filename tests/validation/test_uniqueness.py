"""Tests for blocking within-file uniqueness validation."""

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from kz_ecomops.validation import (
    CSV_SCHEMAS,
    CsvUniquenessErrorCode,
    CsvUniquenessIssue,
    CsvUniquenessValidationResult,
    CsvValueValidationResult,
    validate_csv_uniqueness,
    validate_csv_values,
)


def _row(filename: str, number: int) -> dict[str, str]:
    source_order_id = f"{number:03}"
    common = {
        "platform": "shopify",
        "order_id": f"shopify:{source_order_id}",
        "source_order_id": source_order_id,
    }
    if filename == "orders.csv":
        return {
            "order_id": common["order_id"],
            "platform": common["platform"],
            "source_order_id": common["source_order_id"],
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
        }
    if filename == "payments.csv":
        return {
            "payment_id": f"payment-{number:03}",
            **common,
            "provider_transaction_id": f"provider-payment-{number:03}",
            "payment_status": "succeeded",
            "amount": "14.20",
            "currency": "EUR",
            "paid_at": "2026-08-14T10:31:00+02:00",
            "created_at": "2026-08-14T10:31:00+02:00",
            "updated_at": "2026-08-14T10:31:00+02:00",
        }
    if filename == "shipments.csv":
        return {
            "shipment_id": f"shipment-{number:03}",
            **common,
            "shipment_status": "pending",
            "updated_at": "2026-08-15T09:00:00+02:00",
        }
    if filename == "returns.csv":
        return {
            "return_id": f"return-{number:03}",
            **common,
            "return_status": "requested",
            "requested_at": "2026-08-20T09:00:00+02:00",
            "updated_at": "2026-08-20T09:00:00+02:00",
        }
    if filename == "refunds.csv":
        return {
            "refund_id": f"refund-{number:03}",
            **common,
            "provider_refund_id": f"provider-refund-{number:03}",
            "refund_status": "succeeded",
            "amount": "14.20",
            "currency": "EUR",
            "refunded_at": "2026-08-23T09:00:00+02:00",
            "created_at": "2026-08-23T09:00:00+02:00",
            "updated_at": "2026-08-23T09:00:00+02:00",
        }
    raise AssertionError(f"Unsupported test filename: {filename}")


def _validated(
    filename: str,
    rows: list[dict[str, str]],
) -> tuple[pd.DataFrame, CsvValueValidationResult, CsvUniquenessValidationResult]:
    dataframe = pd.DataFrame(rows)
    value_result = validate_csv_values(dataframe, CSV_SCHEMAS[filename])
    assert value_result.is_valid
    uniqueness_result = validate_csv_uniqueness(
        dataframe, CSV_SCHEMAS[filename], value_result
    )
    return dataframe, value_result, uniqueness_result


def _only_issue(result: CsvUniquenessValidationResult) -> CsvUniquenessIssue:
    assert result.issue_count == 1
    return result.issues[0]


@pytest.mark.parametrize(
    "filename",
    ("orders.csv", "payments.csv", "shipments.csv", "returns.csv", "refunds.csv"),
)
def test_accepts_file_without_duplicates_for_each_required_csv(filename: str) -> None:
    _, _, result = _validated(filename, [_row(filename, 1), _row(filename, 2)])

    assert result.is_valid
    assert result.row_count == 2
    assert result.valid_row_count == 2


def test_accepts_dataframe_with_zero_rows() -> None:
    schema = CSV_SCHEMAS["orders.csv"]
    dataframe = pd.DataFrame(columns=schema.column_names)
    value_result = validate_csv_values(dataframe, schema)

    result = validate_csv_uniqueness(dataframe, schema, value_result)

    assert result.is_valid
    assert result.row_count == 0
    assert result.invalid_row_numbers == frozenset()


def test_reports_duplicate_order_id_as_one_group() -> None:
    first = _row("orders.csv", 1)
    second = _row("orders.csv", 2)
    second["order_id"] = first["order_id"]

    _, _, result = _validated("orders.csv", [first, second])

    issue = _only_issue(result)
    assert issue.code is CsvUniquenessErrorCode.DUPLICATE_ORDER_ID
    assert issue.row_numbers == (1, 2)
    assert issue.columns == ("order_id",)


def test_reports_duplicate_platform_source_order_key() -> None:
    first = _row("orders.csv", 1)
    second = _row("orders.csv", 2)
    second["platform"] = first["platform"]
    second["source_order_id"] = first["source_order_id"]

    _, _, result = _validated("orders.csv", [first, second])

    issue = _only_issue(result)
    assert issue.code is CsvUniquenessErrorCode.DUPLICATE_SOURCE_ORDER_KEY
    assert issue.row_numbers == (1, 2)
    assert issue.columns == ("platform", "source_order_id")


def test_same_rows_can_violate_both_order_rules() -> None:
    first = _row("orders.csv", 1)
    second = dict(first)

    _, _, result = _validated("orders.csv", [first, second])

    assert result.issue_count == 2
    assert [issue.code for issue in result.issues] == [
        CsvUniquenessErrorCode.DUPLICATE_ORDER_ID,
        CsvUniquenessErrorCode.DUPLICATE_SOURCE_ORDER_KEY,
    ]
    assert all(issue.row_numbers == (1, 2) for issue in result.issues)


def test_non_consecutive_duplicate_group_includes_every_occurrence() -> None:
    rows = [_row("orders.csv", number) for number in range(1, 5)]
    rows[2]["order_id"] = rows[0]["order_id"]

    _, _, result = _validated("orders.csv", rows)

    issue = _only_issue(result)
    assert issue.row_numbers == (1, 3)


def test_duplicate_group_can_contain_three_or_more_rows() -> None:
    rows = [_row("orders.csv", number) for number in range(1, 5)]
    rows[1]["order_id"] = rows[0]["order_id"]
    rows[3]["order_id"] = rows[0]["order_id"]

    _, _, result = _validated("orders.csv", rows)

    issue = _only_issue(result)
    assert issue.row_numbers == (1, 2, 4)


def test_multiple_duplicate_groups_follow_first_occurrence_order() -> None:
    rows = [_row("orders.csv", number) for number in range(1, 5)]
    rows[2]["order_id"] = rows[0]["order_id"]
    rows[3]["order_id"] = rows[1]["order_id"]

    _, _, result = _validated("orders.csv", rows)

    assert [issue.row_numbers for issue in result.issues] == [(1, 3), (2, 4)]


def test_reports_duplicate_shipment_id() -> None:
    first = _row("shipments.csv", 1)
    second = _row("shipments.csv", 2)
    second["shipment_id"] = first["shipment_id"]

    _, _, result = _validated("shipments.csv", [first, second])

    issue = _only_issue(result)
    assert issue.code is CsvUniquenessErrorCode.DUPLICATE_SHIPMENT_ID
    assert issue.columns == ("shipment_id",)


def test_reports_duplicate_return_id() -> None:
    first = _row("returns.csv", 1)
    second = _row("returns.csv", 2)
    second["return_id"] = first["return_id"]

    _, _, result = _validated("returns.csv", [first, second])

    issue = _only_issue(result)
    assert issue.code is CsvUniquenessErrorCode.DUPLICATE_RETURN_ID
    assert issue.columns == ("return_id",)


def test_accepts_repeated_order_reference_in_shipments() -> None:
    first = _row("shipments.csv", 1)
    second = _row("shipments.csv", 2)
    second["order_id"] = first["order_id"]
    second["source_order_id"] = first["source_order_id"]

    _, _, result = _validated("shipments.csv", [first, second])

    assert result.is_valid


def test_accepts_repeated_order_reference_in_returns() -> None:
    first = _row("returns.csv", 1)
    second = _row("returns.csv", 2)
    second["order_id"] = first["order_id"]
    second["source_order_id"] = first["source_order_id"]

    _, _, result = _validated("returns.csv", [first, second])

    assert result.is_valid


def test_accepts_and_preserves_duplicate_payment_id() -> None:
    first = _row("payments.csv", 1)
    second = _row("payments.csv", 2)
    second["payment_id"] = first["payment_id"]
    dataframe, _, result = _validated("payments.csv", [first, second])

    assert result.is_valid
    assert dataframe["payment_id"].tolist() == [first["payment_id"]] * 2
    assert len(dataframe) == 2


def test_accepts_duplicate_provider_transaction_id() -> None:
    first = _row("payments.csv", 1)
    second = _row("payments.csv", 2)
    second["provider_transaction_id"] = first["provider_transaction_id"]

    _, _, result = _validated("payments.csv", [first, second])

    assert result.is_valid


def test_accepts_and_preserves_duplicate_refund_id() -> None:
    first = _row("refunds.csv", 1)
    second = _row("refunds.csv", 2)
    second["refund_id"] = first["refund_id"]
    dataframe, _, result = _validated("refunds.csv", [first, second])

    assert result.is_valid
    assert dataframe["refund_id"].tolist() == [first["refund_id"]] * 2
    assert len(dataframe) == 2


def test_accepts_duplicate_provider_refund_id() -> None:
    first = _row("refunds.csv", 1)
    second = _row("refunds.csv", 2)
    second["provider_refund_id"] = first["provider_refund_id"]

    _, _, result = _validated("refunds.csv", [first, second])

    assert result.is_valid


@pytest.mark.parametrize("filename", ["payments.csv", "refunds.csv"])
def test_accepts_repeated_order_and_source_order_references(filename: str) -> None:
    first = _row(filename, 1)
    second = _row(filename, 2)
    second["order_id"] = first["order_id"]
    second["source_order_id"] = first["source_order_id"]

    _, _, result = _validated(filename, [first, second])

    assert result.is_valid


def test_duplicate_comparison_is_case_sensitive() -> None:
    first = _row("orders.csv", 1)
    second = _row("orders.csv", 2)
    first["order_id"] = "Case-Sensitive-ID"
    second["order_id"] = "case-sensitive-id"

    _, _, result = _validated("orders.csv", [first, second])

    assert result.is_valid


def test_row_numbers_are_positional_and_ignore_dataframe_index() -> None:
    rows = [_row("orders.csv", number) for number in range(1, 4)]
    rows[2]["order_id"] = rows[0]["order_id"]
    dataframe = pd.DataFrame(rows, index=[10, 20, 30])
    value_result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    result = validate_csv_uniqueness(
        dataframe, CSV_SCHEMAS["orders.csv"], value_result
    )

    assert _only_issue(result).row_numbers == (1, 3)


def test_invalid_row_numbers_are_union_of_duplicate_groups() -> None:
    rows = [_row("orders.csv", number) for number in range(1, 5)]
    rows[1]["order_id"] = rows[0]["order_id"]
    rows[2]["platform"] = rows[1]["platform"]
    rows[2]["source_order_id"] = rows[1]["source_order_id"]

    _, _, result = _validated("orders.csv", rows)

    assert result.invalid_row_numbers == frozenset({1, 2, 3})
    assert result.invalid_row_count == 3
    assert result.valid_row_count == 1


def test_issues_follow_rule_then_group_order() -> None:
    rows = [_row("orders.csv", number) for number in range(1, 5)]
    rows[0]["order_id"] = "group-a"
    rows[1]["order_id"] = "group-b"
    rows[2]["order_id"] = "group-b"
    rows[3]["order_id"] = "group-a"
    rows[1]["platform"] = rows[0]["platform"]
    rows[1]["source_order_id"] = rows[0]["source_order_id"]

    _, _, result = _validated("orders.csv", rows)

    assert [(issue.code, issue.row_numbers) for issue in result.issues] == [
        (CsvUniquenessErrorCode.DUPLICATE_ORDER_ID, (1, 4)),
        (CsvUniquenessErrorCode.DUPLICATE_ORDER_ID, (2, 3)),
        (CsvUniquenessErrorCode.DUPLICATE_SOURCE_ORDER_KEY, (1, 2)),
    ]


def test_message_is_useful_without_duplicate_values() -> None:
    private_value = "PRIVATE-DUPLICATE-ID"
    first = _row("orders.csv", 1)
    second = _row("orders.csv", 2)
    first["order_id"] = private_value
    second["order_id"] = private_value

    _, _, result = _validated("orders.csv", [first, second])

    issue = _only_issue(result)
    assert private_value not in issue.message
    assert "orders.csv" in issue.message
    assert "data rows 1, 2" in issue.message
    assert "order_id" in issue.message


def test_validation_does_not_modify_sort_or_remove_rows() -> None:
    first = _row("orders.csv", 1)
    second = _row("orders.csv", 2)
    second["order_id"] = first["order_id"]
    dataframe = pd.DataFrame([first, second], index=[20, 10])
    original = dataframe.copy(deep=True)
    value_result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    result = validate_csv_uniqueness(
        dataframe, CSV_SCHEMAS["orders.csv"], value_result
    )

    pd.testing.assert_frame_equal(dataframe, original)
    assert len(dataframe) == 2
    assert result.row_count == 2


def test_ignores_additional_columns() -> None:
    first = _row("orders.csv", 1)
    second = _row("orders.csv", 2)
    first["external"] = "same"
    second["external"] = "same"

    _, _, result = _validated("orders.csv", [first, second])

    assert result.is_valid


def test_uniqueness_does_not_require_integrity_result() -> None:
    row = _row("orders.csv", 1)
    row["order_id"] = "value-valid-but-not-deterministic"

    _, _, result = _validated("orders.csv", [row])

    assert result.is_valid


def test_csv_uniqueness_issue_is_frozen_and_slotted() -> None:
    issue = CsvUniquenessIssue(
        code=CsvUniquenessErrorCode.DUPLICATE_ORDER_ID,
        filename="orders.csv",
        row_numbers=(1, 2),
        columns=("order_id",),
        message="Correct the duplicate group.",
    )

    with pytest.raises(FrozenInstanceError):
        issue.row_numbers = (1, 2, 3)  # type: ignore[misc]
    assert not hasattr(issue, "__dict__")


def test_csv_uniqueness_result_is_frozen_and_slotted() -> None:
    result = CsvUniquenessValidationResult(
        schema=CSV_SCHEMAS["orders.csv"],
        row_count=0,
    )

    with pytest.raises(FrozenInstanceError):
        result.row_count = 1  # type: ignore[misc]
    assert not hasattr(result, "__dict__")


def test_uniqueness_error_code_values_are_exact() -> None:
    assert {code.value for code in CsvUniquenessErrorCode} == {
        "duplicate_order_id",
        "duplicate_source_order_key",
        "duplicate_shipment_id",
        "duplicate_return_id",
    }


def test_rejects_non_dataframe_input() -> None:
    dataframe = pd.DataFrame([_row("orders.csv", 1)])
    value_result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    with pytest.raises(TypeError, match="pandas DataFrame"):
        validate_csv_uniqueness(
            [],  # type: ignore[arg-type]
            CSV_SCHEMAS["orders.csv"],
            value_result,
        )


def test_rejects_wrong_value_result_type() -> None:
    dataframe = pd.DataFrame([_row("orders.csv", 1)])

    with pytest.raises(TypeError, match="CsvValueValidationResult"):
        validate_csv_uniqueness(
            dataframe,
            CSV_SCHEMAS["orders.csv"],
            None,  # type: ignore[arg-type]
        )


def test_rejects_value_result_for_different_schema() -> None:
    dataframe = pd.DataFrame([_row("orders.csv", 1)])
    value_result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])

    with pytest.raises(
        ValueError,
        match="Value validation must complete successfully before uniqueness validation",
    ):
        validate_csv_uniqueness(
            dataframe,
            CSV_SCHEMAS["payments.csv"],
            value_result,
        )


def test_rejects_value_result_with_different_row_count() -> None:
    dataframe = pd.DataFrame([_row("orders.csv", 1)])
    value_result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
    two_rows = pd.concat([dataframe, dataframe], ignore_index=True)

    with pytest.raises(
        ValueError,
        match="Value validation must complete successfully before uniqueness validation",
    ):
        validate_csv_uniqueness(
            two_rows,
            CSV_SCHEMAS["orders.csv"],
            value_result,
        )


def test_rejects_value_result_containing_issues() -> None:
    invalid_row = _row("orders.csv", 1)
    invalid_row["platform"] = "invalid"
    dataframe = pd.DataFrame([invalid_row])
    value_result = validate_csv_values(dataframe, CSV_SCHEMAS["orders.csv"])
    assert not value_result.is_valid

    with pytest.raises(
        ValueError,
        match="Value validation must complete successfully before uniqueness validation",
    ):
        validate_csv_uniqueness(
            dataframe,
            CSV_SCHEMAS["orders.csv"],
            value_result,
        )
