"""End-to-end tests for complete required-dataset validation."""

import csv
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType

import pandas as pd
import pytest

from kz_ecomops.validation import (
    CSV_SCHEMAS,
    DatasetValidationReport,
    DatasetValidationResult,
    FileValidationReport,
    ValidationMessage,
    ValidationStage,
    validate_dataset_directory,
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


def _valid_rows() -> dict[str, list[dict[str, str]]]:
    return {
        "orders.csv": [_order(1)],
        "payments.csv": [
            {
                "payment_id": "payment-001",
                **_reference(1),
                "payment_status": "succeeded",
                "amount": "14.20",
                "currency": "EUR",
                "paid_at": "2026-08-14T10:31:00+02:00",
                "created_at": "2026-08-14T10:31:00+02:00",
                "updated_at": "2026-08-14T10:31:00+02:00",
            }
        ],
        "shipments.csv": [
            {
                "shipment_id": "shipment-001",
                **_reference(1),
                "shipment_status": "pending",
                "updated_at": "2026-08-15T09:00:00+02:00",
            }
        ],
        "returns.csv": [
            {
                "return_id": "return-001",
                **_reference(1),
                "return_status": "requested",
                "requested_at": "2026-08-20T09:00:00+02:00",
                "updated_at": "2026-08-20T09:00:00+02:00",
            }
        ],
        "refunds.csv": [
            {
                "refund_id": "refund-001",
                **_reference(1),
                "return_id": "return-001",
                "payment_id": "payment-001",
                "refund_status": "succeeded",
                "amount": "14.20",
                "currency": "EUR",
                "refunded_at": "2026-08-23T09:00:00+02:00",
                "created_at": "2026-08-23T09:00:00+02:00",
                "updated_at": "2026-08-23T09:00:00+02:00",
            }
        ],
    }


def _write_csv(
    directory: Path,
    filename: str,
    rows: list[dict[str, str]],
    *,
    fieldnames: tuple[str, ...] | None = None,
) -> None:
    columns = fieldnames or CSV_SCHEMAS[filename].column_names
    with (directory / filename).open(
        mode="w", encoding="utf-8", newline=""
    ) as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _write_dataset(
    directory: Path,
    rows_by_file: dict[str, list[dict[str, str]]] | None = None,
    *,
    skip: frozenset[str] = frozenset(),
) -> None:
    rows_by_file = rows_by_file or _valid_rows()
    for filename in CSV_SCHEMAS:
        if filename not in skip:
            _write_csv(directory, filename, rows_by_file.get(filename, []))


def test_validates_complete_five_file_directory(tmp_path: Path) -> None:
    _write_dataset(tmp_path)

    result = validate_dataset_directory(tmp_path)

    assert result.report.is_valid
    assert result.report.reconciliation_ready
    assert result.report.blocking_message_count == 0
    assert result.report.relationship_finding_count == 0
    assert result.report.total_row_count == 5
    assert result.report.accepted_row_count == 5
    assert result.report.rejected_row_count == 0
    assert result.dataframes is not None
    assert tuple(result.dataframes) == tuple(CSV_SCHEMAS)


@pytest.mark.parametrize("use_string", [False, True])
def test_accepts_path_and_string_directory(tmp_path: Path, use_string: bool) -> None:
    _write_dataset(tmp_path)
    directory: str | Path = str(tmp_path) if use_string else tmp_path

    result = validate_dataset_directory(directory)

    assert result.report.reconciliation_ready


def test_accepts_five_header_only_files(tmp_path: Path) -> None:
    _write_dataset(tmp_path, {filename: [] for filename in CSV_SCHEMAS})

    result = validate_dataset_directory(tmp_path)

    assert result.report.reconciliation_ready
    assert result.report.total_row_count == 0
    assert result.dataframes is not None
    assert all(dataframe.empty for dataframe in result.dataframes.values())


def test_reports_missing_required_file_as_blocking_read_error(tmp_path: Path) -> None:
    _write_dataset(tmp_path, skip=frozenset({"refunds.csv"}))

    result = validate_dataset_directory(tmp_path)
    file_report = result.report.get_file("refunds.csv")

    assert not file_report.is_valid
    assert file_report.row_count == 0
    assert file_report.accepted_row_count == 0
    assert file_report.rejected_row_count == 0
    assert file_report.messages[0].stage is ValidationStage.READ
    assert file_report.messages[0].blocking
    assert result.dataframes is None
    assert not result.report.reconciliation_ready


def test_reports_structurally_invalid_header(tmp_path: Path) -> None:
    _write_dataset(tmp_path)
    _write_csv(
        tmp_path,
        "orders.csv",
        [{"platform": "shopify"}],
        fieldnames=("platform",),
    )

    result = validate_dataset_directory(tmp_path)
    file_report = result.report.get_file("orders.csv")

    assert file_report.messages[0].stage is ValidationStage.READ
    assert file_report.row_count == 0
    assert result.dataframes is None


def test_reports_invalid_cell_value_and_stops_later_file_stages(
    tmp_path: Path,
) -> None:
    rows = _valid_rows()
    rows["orders.csv"][0]["currency"] = "USD"
    _write_dataset(tmp_path, rows)

    result = validate_dataset_directory(tmp_path)
    file_report = result.report.get_file("orders.csv")

    assert [message.stage for message in file_report.messages] == [
        ValidationStage.VALUE
    ]
    assert file_report.rejected_row_count == 1
    assert result.dataframes is None


def test_reports_integrity_problem_as_blocking(tmp_path: Path) -> None:
    rows = _valid_rows()
    rows["payments.csv"][0]["paid_at"] = ""
    _write_dataset(tmp_path, rows)

    result = validate_dataset_directory(tmp_path)
    file_report = result.report.get_file("payments.csv")

    assert [message.stage for message in file_report.messages] == [
        ValidationStage.INTEGRITY
    ]
    assert file_report.rejected_row_count == 1
    assert result.dataframes is None


def test_reports_blocking_duplicate_group(tmp_path: Path) -> None:
    rows = _valid_rows()
    rows["orders.csv"].append(dict(rows["orders.csv"][0]))
    _write_dataset(tmp_path, rows)

    result = validate_dataset_directory(tmp_path)
    file_report = result.report.get_file("orders.csv")

    assert all(
        message.stage is ValidationStage.UNIQUENESS
        for message in file_report.messages
    )
    assert file_report.row_count == 2
    assert file_report.rejected_row_count == 2
    assert file_report.accepted_row_count == 0
    assert result.dataframes is None


def test_multiple_errors_on_same_row_are_rejected_once(tmp_path: Path) -> None:
    rows = _valid_rows()
    rows["orders.csv"][0]["platform"] = "invalid"
    rows["orders.csv"][0]["currency"] = "USD"
    _write_dataset(tmp_path, rows)

    result = validate_dataset_directory(tmp_path)
    file_report = result.report.get_file("orders.csv")

    assert file_report.blocking_message_count == 2
    assert file_report.rejected_row_count == 1
    assert file_report.accepted_row_count == 0


def test_relationship_finding_is_non_blocking_and_keeps_dataframes(
    tmp_path: Path,
) -> None:
    rows = {filename: [] for filename in CSV_SCHEMAS}
    rows["orders.csv"] = [_order(1)]
    missing_reference = {
        "payment_id": "payment-private",
        **_reference(2),
        "payment_status": "succeeded",
        "amount": "14.20",
        "currency": "EUR",
        "paid_at": "2026-08-14T10:31:00+02:00",
        "created_at": "2026-08-14T10:31:00+02:00",
        "updated_at": "2026-08-14T10:31:00+02:00",
    }
    rows["payments.csv"] = [missing_reference]
    _write_dataset(tmp_path, rows)

    result = validate_dataset_directory(tmp_path)
    payment_report = result.report.get_file("payments.csv")

    assert payment_report.is_valid
    assert payment_report.rejected_row_count == 0
    assert payment_report.accepted_row_count == 1
    assert payment_report.relationship_finding_count == 1
    assert payment_report.messages[0].stage is ValidationStage.RELATIONSHIP
    assert not payment_report.messages[0].blocking
    assert result.report.reconciliation_ready
    assert result.dataframes is not None


def test_returned_dataframe_mapping_is_read_only(tmp_path: Path) -> None:
    _write_dataset(tmp_path)
    result = validate_dataset_directory(tmp_path)

    assert isinstance(result.dataframes, MappingProxyType)
    assert result.dataframes is not None
    with pytest.raises(TypeError):
        result.dataframes["extra.csv"] = pd.DataFrame()  # type: ignore[index]


def test_ignores_additional_files(tmp_path: Path) -> None:
    _write_dataset(tmp_path)
    extra_file = tmp_path / "extra.csv"
    extra_file.write_text("private,value\n", encoding="utf-8")

    result = validate_dataset_directory(tmp_path)

    assert result.report.reconciliation_ready
    assert tuple(file.filename for file in result.report.files) == tuple(CSV_SCHEMAS)
    assert result.dataframes is not None
    assert "extra.csv" not in result.dataframes


def test_rejects_nonexistent_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        validate_dataset_directory(tmp_path / "missing")


def test_rejects_path_that_is_not_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "dataset.csv"
    file_path.write_text("header\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        validate_dataset_directory(file_path)


def test_file_and_message_order_is_deterministic(tmp_path: Path) -> None:
    rows = {filename: [] for filename in CSV_SCHEMAS}
    rows["payments.csv"] = [
        {
            "payment_id": "payment-001",
            **_reference(1),
            "payment_status": "succeeded",
            "amount": "14.20",
            "currency": "EUR",
            "paid_at": "2026-08-14T10:31:00+02:00",
            "created_at": "2026-08-14T10:31:00+02:00",
            "updated_at": "2026-08-14T10:31:00+02:00",
        }
    ]
    rows["shipments.csv"] = [
        {
            "shipment_id": "shipment-002",
            **_reference(2),
            "shipment_status": "pending",
            "updated_at": "2026-08-15T09:00:00+02:00",
        }
    ]
    _write_dataset(tmp_path, rows)

    result = validate_dataset_directory(tmp_path)

    assert tuple(report.filename for report in result.report.files) == tuple(
        CSV_SCHEMAS
    )
    assert [(message.filename, message.row_numbers) for message in result.report.messages] == [
        ("payments.csv", (1,)),
        ("shipments.csv", (1,)),
    ]


def test_file_and_dataset_counts_are_consistent(tmp_path: Path) -> None:
    rows = _valid_rows()
    rows["orders.csv"].append(_order(2))
    rows["orders.csv"][1]["currency"] = "USD"
    _write_dataset(tmp_path, rows)

    result = validate_dataset_directory(tmp_path)
    order_report = result.report.get_file("orders.csv")

    assert order_report.row_count == 2
    assert order_report.accepted_row_count == 1
    assert order_report.rejected_row_count == 1
    assert result.report.total_row_count == 6
    assert result.report.accepted_row_count == 5
    assert result.report.rejected_row_count == 1


def test_get_file_raises_descriptive_error_for_unknown_name(tmp_path: Path) -> None:
    _write_dataset(tmp_path)
    result = validate_dataset_directory(tmp_path)

    with pytest.raises(KeyError, match="No validation report exists"):
        result.report.get_file("unknown.csv")


def test_messages_do_not_expose_original_values(tmp_path: Path) -> None:
    private_source = "PRIVATE-SOURCE-ID"
    rows = {filename: [] for filename in CSV_SCHEMAS}
    rows["payments.csv"] = [
        {
            "payment_id": "payment-001",
            "platform": "shopify",
            "order_id": f"shopify:{private_source}",
            "source_order_id": private_source,
            "payment_status": "succeeded",
            "amount": "14.20",
            "currency": "EUR",
            "paid_at": "2026-08-14T10:31:00+02:00",
            "created_at": "2026-08-14T10:31:00+02:00",
            "updated_at": "2026-08-14T10:31:00+02:00",
        }
    ]
    _write_dataset(tmp_path, rows)

    result = validate_dataset_directory(tmp_path)

    assert result.report.messages
    assert all(private_source not in message.message for message in result.report.messages)


def test_source_csv_files_are_not_modified(tmp_path: Path) -> None:
    _write_dataset(tmp_path)
    original_bytes = {
        filename: (tmp_path / filename).read_bytes() for filename in CSV_SCHEMAS
    }

    validate_dataset_directory(tmp_path)

    assert {
        filename: (tmp_path / filename).read_bytes() for filename in CSV_SCHEMAS
    } == original_bytes


def test_validation_stage_values_are_exact() -> None:
    assert {stage.value for stage in ValidationStage} == {
        "read",
        "value",
        "integrity",
        "uniqueness",
        "relationship",
    }


def test_report_dataclasses_are_frozen_and_slotted() -> None:
    message = ValidationMessage(
        stage=ValidationStage.READ,
        code="file_not_found",
        filename="orders.csv",
        row_numbers=(),
        columns=(),
        message="Provide the file.",
        blocking=True,
    )
    file_report = FileValidationReport(
        filename="orders.csv",
        row_count=0,
        accepted_row_count=0,
        rejected_row_count=0,
        messages=(message,),
    )
    report = DatasetValidationReport(files=(file_report,))
    result = DatasetValidationResult(report=report, dataframes=None)

    for instance, attribute, replacement in (
        (message, "blocking", False),
        (file_report, "row_count", 1),
        (report, "files", ()),
        (result, "dataframes", {}),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, attribute, replacement)
        assert not hasattr(instance, "__dict__")


def test_manual_report_properties_distinguish_blocking_and_relationship() -> None:
    messages = (
        ValidationMessage(
            stage=ValidationStage.VALUE,
            code="invalid_allowed_value",
            filename="orders.csv",
            row_numbers=(1,),
            columns=("currency",),
            message="Correct the value.",
            blocking=True,
        ),
        ValidationMessage(
            stage=ValidationStage.RELATIONSHIP,
            code="order_reference_not_found",
            filename="orders.csv",
            row_numbers=(2,),
            columns=("order_id",),
            message="Review the relationship.",
            blocking=False,
        ),
    )
    file_report = FileValidationReport(
        filename="orders.csv",
        row_count=2,
        accepted_row_count=1,
        rejected_row_count=1,
        messages=messages,
    )

    assert not file_report.is_valid
    assert file_report.blocking_message_count == 1
    assert file_report.relationship_finding_count == 1
