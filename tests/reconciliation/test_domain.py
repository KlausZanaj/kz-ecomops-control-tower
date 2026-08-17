"""Tests for immutable deterministic reconciliation domain objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest

from kz_ecomops.reconciliation import (
    AnomalyCode,
    ProblemType,
    RecordReference,
    ReconciliationAnomaly,
    ReconciliationConfig,
    ReconciliationResult,
    ReviewStatus,
    RuleCode,
    RuleNotEvaluated,
    Severity,
    deterministic_anomaly_id,
)
from kz_ecomops.reconciliation.context import ReconciliationContext
from kz_ecomops.validation import CSV_SCHEMAS


REFERENCE_AT = datetime(2026, 3, 20, 12, tzinfo=timezone.utc)


def _reference(filename: str = "orders.csv", row_number: int = 1) -> RecordReference:
    return RecordReference(filename, row_number, f"record-{row_number}")


def _anomaly(
    code: AnomalyCode = AnomalyCode.PAYMENT_AMOUNT_MISMATCH,
    *,
    platform: str = "shopify",
    status: ReviewStatus = ReviewStatus.OPEN,
) -> ReconciliationAnomaly:
    rule_code = RuleCode[f"REC_{list(AnomalyCode).index(code) + 1:02d}"]
    reference = _reference(row_number=list(AnomalyCode).index(code) + 1)
    return ReconciliationAnomaly(
        anomaly_id=deterministic_anomaly_id(rule_code, (reference,)),
        rule_code=rule_code,
        anomaly_code=code,
        order_id=f"{platform}:ORDER-1",
        platform=platform,
        problem_type=ProblemType.FINANCIAL,
        description="A deterministic discrepancy was found.",
        severity=Severity.HIGH,
        detected_at=REFERENCE_AT,
        recommended_action="Review the referenced source records.",
        review_status=status,
        compared_values={"expected": "100.00", "actual": "90.00"},
        record_references=(reference,),
    )


def test_public_enums_have_exact_values() -> None:
    assert [item.value for item in RuleCode] == [f"REC-{number:02d}" for number in range(1, 11)]
    assert [item.value for item in AnomalyCode] == [
        "PAYMENT_AMOUNT_MISMATCH",
        "PAID_NOT_SHIPPED_ON_TIME",
        "SHIPPED_WITHOUT_CONFIRMED_PAYMENT",
        "DUPLICATE_PAYMENT",
        "SHIPMENT_WITHOUT_TRACKING",
        "CANCELLED_ORDER_SHIPPED",
        "RETURN_RECEIVED_NOT_REFUNDED",
        "REFUND_EXCEEDS_PAYMENT",
        "DUPLICATE_REFUND",
        "CROSS_SYSTEM_RECORD_MISSING",
    ]
    assert [item.value for item in Severity] == ["critical", "high", "medium", "low"]
    assert [item.value for item in ReviewStatus] == ["open", "in_review", "resolved", "dismissed"]


@pytest.mark.parametrize(
    "model",
    [
        RecordReference,
        ReconciliationAnomaly,
        RuleNotEvaluated,
        ReconciliationConfig,
        ReconciliationResult,
    ],
)
def test_public_dataclasses_are_frozen_and_slotted(model: type[object]) -> None:
    assert model.__slots__
    assert all(field.init or not field.init for field in fields(model))
    instance = _reference() if model is RecordReference else None
    if instance is not None:
        with pytest.raises(FrozenInstanceError):
            instance.filename = "changed.csv"  # type: ignore[misc]


def test_config_defaults_and_valid_high_threshold() -> None:
    config = ReconciliationConfig()
    assert config.monetary_tolerance == Decimal("0.01")
    assert config.shipping_limit == timedelta(hours=48)
    assert config.return_refund_limit == timedelta(days=7)
    assert config.high_shipping_delay_threshold is None
    assert ReconciliationConfig(
        high_shipping_delay_threshold=timedelta(hours=72)
    ).high_shipping_delay_threshold == timedelta(hours=72)


@pytest.mark.parametrize(
    ("kwargs", "error_type"),
    [
        ({"monetary_tolerance": Decimal("-0.01")}, ValueError),
        ({"monetary_tolerance": Decimal("NaN")}, ValueError),
        ({"monetary_tolerance": 0.01}, TypeError),
        ({"shipping_limit": timedelta(0)}, ValueError),
        ({"return_refund_limit": timedelta(days=-1)}, ValueError),
        ({"high_shipping_delay_threshold": timedelta(hours=48)}, ValueError),
        ({"high_shipping_delay_threshold": timedelta(hours=24)}, ValueError),
    ],
)
def test_invalid_config_is_rejected(kwargs: dict[str, object], error_type: type[Exception]) -> None:
    with pytest.raises(error_type):
        ReconciliationConfig(**kwargs)  # type: ignore[arg-type]


def test_reference_time_must_be_explicitly_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone"):
        ReconciliationResult(datetime(2026, 3, 20), ReconciliationConfig())
    with pytest.raises(ValueError, match="timezone"):
        replace(_anomaly(), detected_at=datetime(2026, 3, 20))


def test_anomaly_id_is_stable_and_reference_order_independent() -> None:
    first = _reference("payments.csv", 2)
    second = _reference("orders.csv", 1)
    expected = deterministic_anomaly_id(
        RuleCode.REC_01, (first, second), discriminator="shopify:ORDER-1"
    )
    assert expected == deterministic_anomaly_id(
        RuleCode.REC_01, (second, first), discriminator="shopify:ORDER-1"
    )
    assert expected != deterministic_anomaly_id(RuleCode.REC_02, (second, first))


def test_anomaly_mappings_and_references_are_protected_and_sorted() -> None:
    anomaly = _anomaly()
    with pytest.raises(TypeError):
        anomaly.compared_values["actual"] = "0.00"  # type: ignore[index]
    assert tuple(anomaly.compared_values) == ("actual", "expected")
    assert anomaly.record_references == tuple(sorted(anomaly.record_references))


def test_result_sorts_items_and_exposes_protected_deterministic_counts() -> None:
    later = _anomaly(AnomalyCode.DUPLICATE_REFUND, platform="woocommerce")
    earlier = _anomaly(AnomalyCode.PAYMENT_AMOUNT_MISMATCH)
    unavailable = RuleNotEvaluated(
        RuleCode.REC_07,
        "shopify:ORDER-2",
        "shopify",
        "Expected refund amount is unavailable.",
        (_reference("returns.csv", 3),),
    )
    result = ReconciliationResult(
        REFERENCE_AT,
        ReconciliationConfig(),
        anomalies=(later, earlier),
        not_evaluated=(unavailable,),
    )

    assert result.anomalies == (earlier, later)
    assert result.counts_by_code == {
        AnomalyCode.PAYMENT_AMOUNT_MISMATCH: 1,
        AnomalyCode.DUPLICATE_REFUND: 1,
    }
    assert result.counts_by_severity == {Severity.HIGH: 2}
    assert result.counts_by_platform == {"shopify": 1, "woocommerce": 1}
    assert result.counts_by_status == {ReviewStatus.OPEN: 2}
    assert result.not_evaluated_counts == {RuleCode.REC_07: 1}
    with pytest.raises(TypeError):
        result.counts_by_platform["shopify"] = 2  # type: ignore[index]


def test_result_rejects_duplicate_anomaly_ids() -> None:
    anomaly = _anomaly()
    with pytest.raises(ValueError, match="duplicate anomaly IDs"):
        ReconciliationResult(
            REFERENCE_AT,
            ReconciliationConfig(),
            anomalies=(anomaly, anomaly),
        )


def test_context_builds_indexes_once_without_modifying_dataframes() -> None:
    frames = {
        filename: pd.DataFrame(columns=schema.column_names, dtype=str)
        for filename, schema in CSV_SCHEMAS.items()
    }
    frames["orders.csv"] = pd.DataFrame(
        [{column: "" for column in CSV_SCHEMAS["orders.csv"].column_names}],
        dtype=str,
    )
    frames["orders.csv"].loc[0, ["order_id", "platform", "source_order_id"]] = [
        "shopify:ORDER-1",
        "shopify",
        "ORDER-1",
    ]
    originals = {name: frame.copy(deep=True) for name, frame in frames.items()}

    context = ReconciliationContext.from_dataframes(frames)

    assert context.orders_by_id["shopify:ORDER-1"].get("platform") == "shopify"
    for filename in frames:
        pd.testing.assert_frame_equal(frames[filename], originals[filename])
