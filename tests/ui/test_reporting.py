"""Pure integration tests for filtered UI anomaly reporting."""

from __future__ import annotations

import csv
import io
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from kz_ecomops.reconciliation import (
    AnomalyCode,
    ProblemType,
    ReconciliationAnomaly,
    ReconciliationConfig,
    ReconciliationResult,
    ReviewStatus,
    RuleCode,
    Severity,
)
from kz_ecomops.ui import build_filtered_anomaly_report


REFERENCE_AT = datetime(2026, 3, 20, 12, tzinfo=timezone.utc)


def _anomaly(
    anomaly_id: str,
    *,
    anomaly_code: AnomalyCode,
    platform: str,
    severity: Severity,
    review_status: ReviewStatus,
) -> ReconciliationAnomaly:
    return ReconciliationAnomaly(
        anomaly_id=anomaly_id,
        rule_code=RuleCode.REC_01,
        anomaly_code=anomaly_code,
        order_id=f"{platform}:ORDER-{anomaly_id}",
        platform=platform,
        problem_type=ProblemType.FINANCIAL,
        description="Synthetic filtered export anomaly.",
        severity=severity,
        detected_at=REFERENCE_AT,
        recommended_action="Review the synthetic anomaly.",
        review_status=review_status,
    )


def _result(
    anomalies: tuple[ReconciliationAnomaly, ...] | None = None,
) -> ReconciliationResult:
    selected = anomalies or (
        _anomaly(
            "a-1",
            anomaly_code=AnomalyCode.PAYMENT_AMOUNT_MISMATCH,
            platform="shopify",
            severity=Severity.HIGH,
            review_status=ReviewStatus.OPEN,
        ),
        _anomaly(
            "a-2",
            anomaly_code=AnomalyCode.PAYMENT_AMOUNT_MISMATCH,
            platform="amazon",
            severity=Severity.HIGH,
            review_status=ReviewStatus.IN_REVIEW,
        ),
        _anomaly(
            "a-3",
            anomaly_code=AnomalyCode.SHIPMENT_WITHOUT_TRACKING,
            platform="shopify",
            severity=Severity.MEDIUM,
            review_status=ReviewStatus.RESOLVED,
        ),
    )
    return ReconciliationResult(
        reference_at=REFERENCE_AT,
        config=ReconciliationConfig(
            monetary_tolerance=Decimal("0.01"),
            shipping_limit=timedelta(hours=48),
            return_refund_limit=timedelta(days=7),
        ),
        anomalies=selected,
    )


def _rows(content: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))


def test_no_filter_single_filter_combined_filter_and_zero_results() -> None:
    result = _result()

    all_items = build_filtered_anomaly_report(result)
    shopify = build_filtered_anomaly_report(result, platforms={"shopify"})
    combined = build_filtered_anomaly_report(
        result,
        platforms={"shopify"},
        severities={"high"},
    )
    empty = build_filtered_anomaly_report(
        result,
        platforms={"amazon"},
        severities={"medium"},
    )

    assert all_items.export.row_count == 3
    assert {row["anomaly_id"] for row in _rows(all_items.export.content)} == {
        "a-1",
        "a-2",
        "a-3",
    }
    assert shopify.export.row_count == 2
    assert [item.anomaly_id for item in combined.anomalies] == ["a-1"]
    assert combined.export.row_count == 1
    assert empty.anomalies == ()
    assert empty.export.row_count == 0
    assert _rows(empty.export.content) == []
    assert len(
        {
            all_items.export.content,
            shopify.export.content,
            combined.export.content,
            empty.export.content,
        }
    ) == 4


def test_filtered_export_uses_updated_status_and_real_result_context() -> None:
    original = _result()
    updated_anomalies = tuple(
        replace(item, review_status=ReviewStatus.RESOLVED)
        if item.anomaly_id == "a-1"
        else item
        for item in original.anomalies
    )
    updated = replace(original, anomalies=updated_anomalies)

    report = build_filtered_anomaly_report(
        updated,
        review_statuses={"resolved"},
    )
    rows = _rows(report.export.content)

    assert report.export.row_count == 2
    assert {row["anomaly_id"] for row in rows} == {"a-1", "a-3"}
    assert {row["review_status"] for row in rows} == {"resolved"}
    assert {row["reference_at"] for row in rows} == {
        "2026-03-20T12:00:00+00:00"
    }
    assert {row["monetary_tolerance"] for row in rows} == {"0.01"}


def test_filtering_and_export_do_not_mutate_state_or_write_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = _result()
    original_anomalies = result.anomalies

    report = build_filtered_anomaly_report(result, platforms={"shopify"})

    assert report.export.content
    assert result.anomalies == original_anomalies
    assert tuple(tmp_path.iterdir()) == ()
