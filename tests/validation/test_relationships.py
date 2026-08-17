"""Tests for non-blocking cross-file CSV relationship findings."""

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from kz_ecomops.validation import (
    CSV_SCHEMAS,
    CsvIntegrityErrorCode,
    CsvIntegrityIssue,
    CsvIntegrityValidationResult,
    CsvRelationshipFinding,
    CsvRelationshipFindingCode,
    CsvRelationshipValidationResult,
    CsvUniquenessErrorCode,
    CsvUniquenessIssue,
    CsvUniquenessValidationResult,
    CsvValueErrorCode,
    CsvValueIssue,
    CsvValueValidationResult,
    validate_csv_integrity,
    validate_csv_relationships,
    validate_csv_uniqueness,
    validate_csv_values,
)


def _order(number: int) -> dict[str, str]:
    source = f"{number:03}"
    return {
        "order_id": f"shopify:{source}",
        "platform": "shopify",
        "source_order_id": source,
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


def _reference(number: int) -> dict[str, str]:
    source = f"{number:03}"
    return {
        "platform": "shopify",
        "order_id": f"shopify:{source}",
        "source_order_id": source,
    }


def _payment(number: int, payment_id: str | None = None) -> dict[str, str]:
    return {
        "payment_id": payment_id or f"payment-{number:03}",
        **_reference(number),
        "payment_status": "succeeded",
        "amount": "14.20",
        "currency": "EUR",
        "paid_at": "2026-08-14T10:31:00+02:00",
        "created_at": "2026-08-14T10:31:00+02:00",
        "updated_at": "2026-08-14T10:31:00+02:00",
    }


def _shipment(number: int) -> dict[str, str]:
    return {
        "shipment_id": f"shipment-{number:03}",
        **_reference(number),
        "shipment_status": "pending",
        "updated_at": "2026-08-15T09:00:00+02:00",
    }


def _return(number: int) -> dict[str, str]:
    return {
        "return_id": f"return-{number:03}",
        **_reference(number),
        "return_status": "requested",
        "requested_at": "2026-08-20T09:00:00+02:00",
        "updated_at": "2026-08-20T09:00:00+02:00",
    }


def _refund(
    number: int,
    *,
    return_id: str = "",
    payment_id: str = "",
) -> dict[str, str]:
    return {
        "refund_id": f"refund-{number:03}",
        **_reference(number),
        "return_id": return_id,
        "payment_id": payment_id,
        "refund_status": "succeeded",
        "amount": "14.20",
        "currency": "EUR",
        "refunded_at": "2026-08-23T09:00:00+02:00",
        "created_at": "2026-08-23T09:00:00+02:00",
        "updated_at": "2026-08-23T09:00:00+02:00",
    }


def _empty_dataframe(filename: str) -> pd.DataFrame:
    return pd.DataFrame(columns=CSV_SCHEMAS[filename].column_names)


def _empty_dataset() -> dict[str, pd.DataFrame]:
    return {filename: _empty_dataframe(filename) for filename in CSV_SCHEMAS}


def _valid_dataset() -> dict[str, pd.DataFrame]:
    return {
        "orders.csv": pd.DataFrame([_order(1)]),
        "payments.csv": pd.DataFrame([_payment(1)]),
        "shipments.csv": pd.DataFrame([_shipment(1)]),
        "returns.csv": pd.DataFrame([_return(1)]),
        "refunds.csv": pd.DataFrame(
            [_refund(1, return_id="return-001", payment_id="payment-001")]
        ),
    }


def _previous_results(
    dataframes: dict[str, pd.DataFrame],
) -> tuple[
    dict[str, CsvValueValidationResult],
    dict[str, CsvIntegrityValidationResult],
    dict[str, CsvUniquenessValidationResult],
]:
    value_results: dict[str, CsvValueValidationResult] = {}
    integrity_results: dict[str, CsvIntegrityValidationResult] = {}
    uniqueness_results: dict[str, CsvUniquenessValidationResult] = {}
    for filename, schema in CSV_SCHEMAS.items():
        dataframe = dataframes[filename]
        value_result = validate_csv_values(dataframe, schema)
        assert value_result.is_valid
        integrity_result = validate_csv_integrity(dataframe, schema, value_result)
        assert integrity_result.is_valid
        uniqueness_result = validate_csv_uniqueness(dataframe, schema, value_result)
        assert uniqueness_result.is_valid
        value_results[filename] = value_result
        integrity_results[filename] = integrity_result
        uniqueness_results[filename] = uniqueness_result
    return value_results, integrity_results, uniqueness_results


def _validate(
    dataframes: dict[str, pd.DataFrame],
) -> CsvRelationshipValidationResult:
    value_results, integrity_results, uniqueness_results = _previous_results(
        dataframes
    )
    return validate_csv_relationships(
        dataframes,
        value_results,
        integrity_results,
        uniqueness_results,
    )


def test_accepts_valid_five_file_dataset() -> None:
    result = _validate(_valid_dataset())

    assert not result.has_findings
    assert result.finding_count == 0
    assert result.affected_records == frozenset()


def test_accepts_five_empty_dataframes() -> None:
    result = _validate(_empty_dataset())

    assert not result.has_findings


@pytest.mark.parametrize(
    "filename,row_factory",
    [
        ("payments.csv", _payment),
        ("shipments.csv", _shipment),
        ("returns.csv", _return),
        ("refunds.csv", _refund),
    ],
)
def test_reports_missing_order_from_each_linked_file(
    filename: str,
    row_factory: object,
) -> None:
    dataframes = _empty_dataset()
    dataframes["orders.csv"] = pd.DataFrame([_order(1)])
    row = row_factory(2)  # type: ignore[operator]
    dataframes[filename] = pd.DataFrame([row])

    result = _validate(dataframes)

    assert result.finding_count == 1
    finding = result.findings[0]
    assert finding.code is CsvRelationshipFindingCode.ORDER_REFERENCE_NOT_FOUND
    assert finding.filename == filename
    assert finding.related_filename == "orders.csv"


@pytest.mark.parametrize("column", ["platform", "source_order_id"])
def test_reports_order_reference_detail_mismatch(column: str) -> None:
    dataframes = _empty_dataset()
    dataframes["orders.csv"] = pd.DataFrame([_order(1)])
    payment = _payment(1)
    payment[column] = "amazon" if column == "platform" else "different"
    dataframes["payments.csv"] = pd.DataFrame([payment])
    value_results, integrity_results, uniqueness_results = _previous_results(
        {**dataframes, "payments.csv": _empty_dataframe("payments.csv")}
    )
    payment_values = validate_csv_values(
        dataframes["payments.csv"], CSV_SCHEMAS["payments.csv"]
    )
    assert payment_values.is_valid
    value_results["payments.csv"] = payment_values
    integrity_results["payments.csv"] = CsvIntegrityValidationResult(
        schema=CSV_SCHEMAS["payments.csv"], row_count=1
    )
    uniqueness_results["payments.csv"] = validate_csv_uniqueness(
        dataframes["payments.csv"],
        CSV_SCHEMAS["payments.csv"],
        payment_values,
    )

    result = validate_csv_relationships(
        dataframes, value_results, integrity_results, uniqueness_results
    )

    assert result.finding_count == 1
    assert (
        result.findings[0].code
        is CsvRelationshipFindingCode.ORDER_REFERENCE_DETAILS_MISMATCH
    )


def test_empty_return_reference_does_not_create_finding() -> None:
    dataframes = _valid_dataset()
    dataframes["refunds.csv"] = pd.DataFrame(
        [_refund(1, return_id="", payment_id="payment-001")]
    )

    result = _validate(dataframes)

    assert not result.has_findings


def test_reports_missing_return_reference() -> None:
    dataframes = _valid_dataset()
    dataframes["refunds.csv"] = pd.DataFrame(
        [_refund(1, return_id="missing-return", payment_id="")]
    )

    result = _validate(dataframes)

    assert result.findings[0].code is CsvRelationshipFindingCode.RETURN_REFERENCE_NOT_FOUND


def test_reports_return_reference_for_different_order() -> None:
    dataframes = _empty_dataset()
    dataframes["orders.csv"] = pd.DataFrame([_order(1), _order(2)])
    dataframes["returns.csv"] = pd.DataFrame([_return(2)])
    dataframes["refunds.csv"] = pd.DataFrame(
        [_refund(1, return_id="return-002")]
    )

    result = _validate(dataframes)

    assert (
        result.findings[0].code
        is CsvRelationshipFindingCode.RETURN_REFERENCE_ORDER_MISMATCH
    )


def test_empty_payment_reference_does_not_create_finding() -> None:
    dataframes = _valid_dataset()
    dataframes["refunds.csv"] = pd.DataFrame(
        [_refund(1, return_id="return-001", payment_id="")]
    )

    result = _validate(dataframes)

    assert not result.has_findings


def test_reports_missing_payment_reference() -> None:
    dataframes = _valid_dataset()
    dataframes["refunds.csv"] = pd.DataFrame(
        [_refund(1, return_id="", payment_id="missing-payment")]
    )

    result = _validate(dataframes)

    assert (
        result.findings[0].code
        is CsvRelationshipFindingCode.PAYMENT_REFERENCE_NOT_FOUND
    )


def test_reports_payment_reference_for_different_order() -> None:
    dataframes = _empty_dataset()
    dataframes["orders.csv"] = pd.DataFrame([_order(1), _order(2)])
    dataframes["payments.csv"] = pd.DataFrame([_payment(2)])
    dataframes["refunds.csv"] = pd.DataFrame(
        [_refund(1, payment_id="payment-002")]
    )

    result = _validate(dataframes)

    assert (
        result.findings[0].code
        is CsvRelationshipFindingCode.PAYMENT_REFERENCE_ORDER_MISMATCH
    )


def test_duplicate_payment_id_with_one_matching_order_is_accepted() -> None:
    dataframes = _empty_dataset()
    dataframes["orders.csv"] = pd.DataFrame([_order(1), _order(2)])
    dataframes["payments.csv"] = pd.DataFrame(
        [_payment(1, "shared-payment"), _payment(2, "shared-payment")]
    )
    dataframes["refunds.csv"] = pd.DataFrame(
        [_refund(1, payment_id="shared-payment")]
    )

    result = _validate(dataframes)

    assert not result.has_findings
    assert len(dataframes["payments.csv"]) == 2


def test_findings_follow_file_row_and_rule_order() -> None:
    dataframes = _empty_dataset()
    dataframes["payments.csv"] = pd.DataFrame([_payment(1)])
    dataframes["shipments.csv"] = pd.DataFrame([_shipment(2)])
    dataframes["returns.csv"] = pd.DataFrame([_return(3)])
    dataframes["refunds.csv"] = pd.DataFrame(
        [_refund(4, return_id="missing-return", payment_id="missing-payment")]
    )

    result = _validate(dataframes)

    assert [(finding.filename, finding.code) for finding in result.findings] == [
        ("payments.csv", CsvRelationshipFindingCode.ORDER_REFERENCE_NOT_FOUND),
        ("shipments.csv", CsvRelationshipFindingCode.ORDER_REFERENCE_NOT_FOUND),
        ("returns.csv", CsvRelationshipFindingCode.ORDER_REFERENCE_NOT_FOUND),
        ("refunds.csv", CsvRelationshipFindingCode.ORDER_REFERENCE_NOT_FOUND),
        ("refunds.csv", CsvRelationshipFindingCode.RETURN_REFERENCE_NOT_FOUND),
        ("refunds.csv", CsvRelationshipFindingCode.PAYMENT_REFERENCE_NOT_FOUND),
    ]


def test_counts_findings_and_distinct_affected_records() -> None:
    dataframes = _empty_dataset()
    dataframes["payments.csv"] = pd.DataFrame([_payment(1)])
    dataframes["refunds.csv"] = pd.DataFrame(
        [_refund(2, return_id="missing-return", payment_id="missing-payment")]
    )

    result = _validate(dataframes)

    assert result.finding_count == 4
    assert result.affected_records == frozenset(
        {("payments.csv", 1), ("refunds.csv", 1)}
    )
    assert result.affected_record_count == 2


def test_messages_do_not_expose_identifiers() -> None:
    private_source = "PRIVATE-SOURCE-IDENTIFIER"
    dataframes = _empty_dataset()
    payment = _payment(1)
    payment["source_order_id"] = private_source
    payment["order_id"] = f"shopify:{private_source}"
    dataframes["payments.csv"] = pd.DataFrame([payment])

    result = _validate(dataframes)

    assert result.finding_count == 1
    assert private_source not in result.findings[0].message
    assert "payments.csv" in result.findings[0].message
    assert "data row 1" in result.findings[0].message


def test_relationship_validation_does_not_modify_dataframes() -> None:
    dataframes = _valid_dataset()
    originals = {
        filename: dataframe.copy(deep=True)
        for filename, dataframe in dataframes.items()
    }

    _validate(dataframes)

    for filename in CSV_SCHEMAS:
        pd.testing.assert_frame_equal(dataframes[filename], originals[filename])


def test_relationship_finding_is_frozen_and_slotted() -> None:
    finding = CsvRelationshipFinding(
        code=CsvRelationshipFindingCode.ORDER_REFERENCE_NOT_FOUND,
        filename="payments.csv",
        row_number=1,
        columns=("order_id",),
        related_filename="orders.csv",
        message="Review the reference.",
    )

    with pytest.raises(FrozenInstanceError):
        finding.row_number = 2  # type: ignore[misc]
    assert not hasattr(finding, "__dict__")


def test_relationship_result_is_frozen_and_slotted() -> None:
    result = CsvRelationshipValidationResult()

    with pytest.raises(FrozenInstanceError):
        result.findings = ()  # type: ignore[misc]
    assert not hasattr(result, "__dict__")


def test_relationship_finding_code_values_are_exact() -> None:
    assert {code.value for code in CsvRelationshipFindingCode} == {
        "order_reference_not_found",
        "order_reference_details_mismatch",
        "return_reference_not_found",
        "return_reference_order_mismatch",
        "payment_reference_not_found",
        "payment_reference_order_mismatch",
    }


def test_rejects_non_mapping_input() -> None:
    dataframes = _valid_dataset()
    value_results, integrity_results, uniqueness_results = _previous_results(
        dataframes
    )

    with pytest.raises(TypeError, match="must be a mapping"):
        validate_csv_relationships(
            [],  # type: ignore[arg-type]
            value_results,
            integrity_results,
            uniqueness_results,
        )


def test_requires_exactly_five_registered_filenames() -> None:
    dataframes = _valid_dataset()
    value_results, integrity_results, uniqueness_results = _previous_results(
        dataframes
    )
    dataframes.pop("refunds.csv")

    with pytest.raises(ValueError, match="exactly the five registered"):
        validate_csv_relationships(
            dataframes, value_results, integrity_results, uniqueness_results
        )


def test_rejects_non_dataframe_mapping_value() -> None:
    dataframes = _valid_dataset()
    value_results, integrity_results, uniqueness_results = _previous_results(
        dataframes
    )
    dataframes["orders.csv"] = "not-a-dataframe"  # type: ignore[assignment]

    with pytest.raises(TypeError, match="pandas DataFrame"):
        validate_csv_relationships(
            dataframes, value_results, integrity_results, uniqueness_results
        )


@pytest.mark.parametrize(
    "mapping_name",
    ["value_results", "integrity_results", "uniqueness_results"],
)
def test_rejects_wrong_result_type(mapping_name: str) -> None:
    dataframes = _valid_dataset()
    value_results, integrity_results, uniqueness_results = _previous_results(
        dataframes
    )
    mappings = {
        "value_results": value_results,
        "integrity_results": integrity_results,
        "uniqueness_results": uniqueness_results,
    }
    mappings[mapping_name]["orders.csv"] = object()  # type: ignore[assignment]

    with pytest.raises(TypeError, match="must be a"):
        validate_csv_relationships(
            dataframes, value_results, integrity_results, uniqueness_results
        )


def test_rejects_result_with_different_schema() -> None:
    dataframes = _valid_dataset()
    value_results, integrity_results, uniqueness_results = _previous_results(
        dataframes
    )
    value_results["orders.csv"] = CsvValueValidationResult(
        schema=CSV_SCHEMAS["payments.csv"], row_count=1
    )

    with pytest.raises(ValueError, match="different schema"):
        validate_csv_relationships(
            dataframes, value_results, integrity_results, uniqueness_results
        )


def test_rejects_result_with_different_row_count() -> None:
    dataframes = _valid_dataset()
    value_results, integrity_results, uniqueness_results = _previous_results(
        dataframes
    )
    value_results["orders.csv"] = CsvValueValidationResult(
        schema=CSV_SCHEMAS["orders.csv"], row_count=2
    )

    with pytest.raises(ValueError, match="different row count"):
        validate_csv_relationships(
            dataframes, value_results, integrity_results, uniqueness_results
        )


@pytest.mark.parametrize(
    "mapping_name",
    ["value_results", "integrity_results", "uniqueness_results"],
)
def test_rejects_blocking_previous_result(mapping_name: str) -> None:
    dataframes = _valid_dataset()
    value_results, integrity_results, uniqueness_results = _previous_results(
        dataframes
    )
    if mapping_name == "value_results":
        value_results["orders.csv"] = CsvValueValidationResult(
            schema=CSV_SCHEMAS["orders.csv"],
            row_count=1,
            issues=(
                CsvValueIssue(
                    code=CsvValueErrorCode.MISSING_REQUIRED_VALUE,
                    filename="orders.csv",
                    row_number=1,
                    column="order_id",
                    message="Correct the value.",
                ),
            ),
        )
    elif mapping_name == "integrity_results":
        integrity_results["orders.csv"] = CsvIntegrityValidationResult(
            schema=CSV_SCHEMAS["orders.csv"],
            row_count=1,
            issues=(
                CsvIntegrityIssue(
                    code=CsvIntegrityErrorCode.ORDER_ID_MISMATCH,
                    filename="orders.csv",
                    row_number=1,
                    columns=("order_id", "platform", "source_order_id"),
                    message="Correct the row.",
                ),
            ),
        )
    else:
        uniqueness_results["orders.csv"] = CsvUniquenessValidationResult(
            schema=CSV_SCHEMAS["orders.csv"],
            row_count=1,
            issues=(
                CsvUniquenessIssue(
                    code=CsvUniquenessErrorCode.DUPLICATE_ORDER_ID,
                    filename="orders.csv",
                    row_numbers=(1,),
                    columns=("order_id",),
                    message="Correct the duplicates.",
                ),
            ),
        )

    with pytest.raises(ValueError, match="blocking problems"):
        validate_csv_relationships(
            dataframes, value_results, integrity_results, uniqueness_results
        )
