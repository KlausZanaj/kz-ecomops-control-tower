"""Deterministic, spreadsheet-safe anomaly CSV reporting tests."""

from __future__ import annotations

import codecs
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd

from kz_ecomops.reconciliation import (
    AnomalyCode,
    ProblemType,
    ReconciliationAnomaly,
    ReconciliationConfig,
    ReconciliationResult,
    RecordReference,
    ReviewStatus,
    RuleCode,
    Severity,
)
from kz_ecomops.reporting import (
    ANOMALY_EXPORT_COLUMNS,
    anomaly_export_filename,
    build_anomaly_export,
    neutralize_spreadsheet_formula,
)


REFERENCE_AT = datetime(2026, 3, 20, 12, 34, 56, tzinfo=timezone.utc)


def _anomaly(
    anomaly_id: str = "anomaly-1",
    *,
    order_id: str | None = "shopify:ORDER-1",
    platform: str = "shopify",
    description: str = "Payment differs from the order total.",
    recommended_action: str = "Review the payment.",
    review_status: ReviewStatus = ReviewStatus.OPEN,
) -> ReconciliationAnomaly:
    return ReconciliationAnomaly(
        anomaly_id=anomaly_id,
        rule_code=RuleCode.REC_01,
        anomaly_code=AnomalyCode.PAYMENT_AMOUNT_MISMATCH,
        order_id=order_id,
        platform=platform,
        problem_type=ProblemType.FINANCIAL,
        description=description,
        severity=Severity.HIGH,
        detected_at=REFERENCE_AT,
        recommended_action=recommended_action,
        review_status=review_status,
        compared_values={"expected": "100.00", "actual": "90.00"},
        record_references=(
            RecordReference("payments.csv", 3, "PAY-1"),
            RecordReference("orders.csv", 2, "shopify:ORDER-1"),
        ),
    )


def _result(
    *anomalies: ReconciliationAnomaly,
    high_threshold: timedelta | None = timedelta(hours=72),
) -> ReconciliationResult:
    return ReconciliationResult(
        reference_at=REFERENCE_AT,
        config=ReconciliationConfig(
            monetary_tolerance=Decimal("0.010"),
            shipping_limit=timedelta(hours=48),
            return_refund_limit=timedelta(days=7),
            high_shipping_delay_threshold=high_threshold,
        ),
        anomalies=tuple(anomalies),
    )


def _csv_rows(content: bytes) -> list[dict[str, str]]:
    return list(
        csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
    )


def test_export_uses_exact_columns_bom_and_deterministic_filename() -> None:
    result = _result(_anomaly())
    export = build_anomaly_export(result)

    assert export.columns == ANOMALY_EXPORT_COLUMNS
    assert tuple(_csv_rows(export.content)[0]) == ANOMALY_EXPORT_COLUMNS
    assert export.content.startswith(codecs.BOM_UTF8)
    assert export.filename == "kz-ecomops-anomalies-20260320-123456Z.csv"
    assert anomaly_export_filename(result) == export.filename
    decoded = export.content.decode("utf-8-sig")
    assert decoded.endswith("\r\n")
    assert "\n" not in decoded.replace("\r\n", "")


def test_export_preserves_unicode_commas_quotes_and_newlines() -> None:
    description = 'Rimborso già verificato, ma contiene "note"\nSeconda riga: città.'
    anomaly = _anomaly(
        description=description,
        recommended_action="Verificare l’operazione con José.",
    )

    row = _csv_rows(build_anomaly_export(_result(anomaly)).content)[0]

    assert row["description"] == description
    assert row["recommended_action"] == "Verificare l’operazione con José."


def test_formula_injection_is_neutralized_only_for_text_cells() -> None:
    anomaly = _anomaly(
        anomaly_id="=ANOMALY()",
        order_id="  +ORDER()",
        platform="@platform",
        description=" -DANGEROUS()",
        recommended_action="=ACTION()",
    )

    row = _csv_rows(build_anomaly_export(_result(anomaly)).content)[0]

    assert row["anomaly_id"] == "'=ANOMALY()"
    assert row["order_id"] == "'  +ORDER()"
    assert row["platform"] == "'@platform"
    assert row["description"] == "' -DANGEROUS()"
    assert row["recommended_action"] == "'=ACTION()"
    assert row["detected_at"] == REFERENCE_AT.isoformat()
    assert row["monetary_tolerance"] == "0.010"
    assert row["compared_values_json"].startswith("{")
    assert neutralize_spreadsheet_formula("ordinary text") == "ordinary text"


def test_context_decimal_dates_durations_and_optional_threshold_are_exact() -> None:
    configured = _csv_rows(build_anomaly_export(_result(_anomaly())).content)[0]
    no_high = _csv_rows(
        build_anomaly_export(_result(_anomaly(), high_threshold=None)).content
    )[0]

    assert configured["reference_at"] == "2026-03-20T12:34:56+00:00"
    assert configured["detected_at"] == "2026-03-20T12:34:56+00:00"
    assert configured["monetary_tolerance"] == "0.010"
    assert configured["currency"] == "EUR"
    assert configured["shipping_limit_hours"] == "48"
    assert configured["return_refund_limit_days"] == "7"
    assert configured["high_shipping_delay_threshold_hours"] == "72"
    assert no_high["high_shipping_delay_threshold_hours"] == ""


def test_json_is_deterministic_and_references_are_complete() -> None:
    row = _csv_rows(build_anomaly_export(_result(_anomaly())).content)[0]

    assert row["compared_values_json"] == (
        '{"actual":"90.00","expected":"100.00"}'
    )
    references = json.loads(row["record_references_json"])
    assert references == [
        {
            "filename": "orders.csv",
            "record_id": "shopify:ORDER-1",
            "row_number": 2,
        },
        {
            "filename": "payments.csv",
            "record_id": "PAY-1",
            "row_number": 3,
        },
    ]


def test_same_and_reordered_inputs_produce_identical_bytes_without_mutation() -> None:
    first = _anomaly("anomaly-b")
    second = _anomaly("anomaly-a", order_id=None)
    result = _result(first, second)
    original_result = result
    original_anomalies = result.anomalies

    all_export = build_anomaly_export(result)
    repeated = build_anomaly_export(result)
    reversed_export = build_anomaly_export(result, reversed(result.anomalies))

    assert all_export.content == repeated.content == reversed_export.content
    assert [row["anomaly_id"] for row in all_export.rows] == [
        "anomaly-a",
        "anomaly-b",
    ]
    assert all_export.rows[0]["order_id"] == ""
    assert result is original_result
    assert result.anomalies == original_anomalies
    assert first.description == "Payment differs from the order total."


def test_zero_one_and_multiple_exports_are_valid_with_csv_and_pandas() -> None:
    empty = build_anomaly_export(_result())
    single = build_anomaly_export(_result(_anomaly()))
    multiple = build_anomaly_export(
        _result(_anomaly("anomaly-2"), _anomaly("anomaly-1"))
    )

    assert empty.row_count == 0
    assert _csv_rows(empty.content) == []
    assert single.row_count == 1
    assert multiple.row_count == 2
    dataframe = pd.read_csv(
        io.BytesIO(multiple.content),
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )
    assert tuple(dataframe.columns) == ANOMALY_EXPORT_COLUMNS
    assert dataframe["anomaly_id"].tolist() == ["anomaly-1", "anomaly-2"]


def test_export_is_entirely_in_memory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    before = tuple(tmp_path.iterdir())

    export = build_anomaly_export(_result(_anomaly()))

    assert export.content
    assert tuple(tmp_path.iterdir()) == before == ()
