"""Tests for stable operational anomaly distributions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from kz_ecomops.reconciliation import (
    AnomalyCode,
    ProblemType,
    ReconciliationAnomaly,
    ReviewStatus,
    RuleCode,
    Severity,
)
from kz_ecomops.reporting import anomaly_distributions


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
        description="Synthetic distribution test anomaly.",
        severity=severity,
        detected_at=REFERENCE_AT,
        recommended_action="Review the synthetic anomaly.",
        review_status=review_status,
    )


def _anomalies() -> tuple[ReconciliationAnomaly, ...]:
    return (
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


def test_distributions_cover_all_dimensions_with_stable_order() -> None:
    anomalies = _anomalies()
    original = tuple(anomalies)

    distributions = anomaly_distributions(anomalies)
    reordered = anomaly_distributions(reversed(anomalies))

    assert distributions.total_count == 3
    assert dict(distributions.by_anomaly_code) == {
        "PAYMENT_AMOUNT_MISMATCH": 2,
        "SHIPMENT_WITHOUT_TRACKING": 1,
    }
    assert dict(distributions.by_severity) == {"high": 2, "medium": 1}
    assert dict(distributions.by_platform) == {"amazon": 1, "shopify": 2}
    assert dict(distributions.by_review_status) == {
        "in_review": 1,
        "open": 1,
        "resolved": 1,
    }
    assert tuple(distributions.by_platform) == ("amazon", "shopify")
    assert distributions == reordered
    assert anomalies == original


def test_filtered_and_empty_distributions_report_real_zero_counts() -> None:
    anomalies = _anomalies()
    filtered = tuple(
        item
        for item in anomalies
        if item.platform == "shopify" and item.severity is Severity.MEDIUM
    )

    selected = anomaly_distributions(filtered)
    empty = anomaly_distributions(())

    assert selected.total_count == 1
    assert dict(selected.by_platform) == {"shopify": 1}
    assert dict(selected.by_severity) == {"medium": 1}
    assert empty.total_count == 0
    assert not empty.by_anomaly_code
    assert not empty.by_severity
    assert not empty.by_platform
    assert not empty.by_review_status


def test_distributions_use_updated_review_status() -> None:
    anomalies = _anomalies()
    updated = (
        replace(anomalies[0], review_status=ReviewStatus.DISMISSED),
        *anomalies[1:],
    )

    distributions = anomaly_distributions(updated)

    assert dict(distributions.by_review_status) == {
        "dismissed": 1,
        "in_review": 1,
        "resolved": 1,
    }
