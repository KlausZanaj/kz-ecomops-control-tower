"""Immutable public domain objects for deterministic reconciliation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType


class RuleCode(StrEnum):
    """Stable reconciliation rule identifiers."""

    REC_01 = "REC-01"
    REC_02 = "REC-02"
    REC_03 = "REC-03"
    REC_04 = "REC-04"
    REC_05 = "REC-05"
    REC_06 = "REC-06"
    REC_07 = "REC-07"
    REC_08 = "REC-08"
    REC_09 = "REC-09"
    REC_10 = "REC-10"


class AnomalyCode(StrEnum):
    """Stable business anomaly identifiers."""

    PAYMENT_AMOUNT_MISMATCH = "PAYMENT_AMOUNT_MISMATCH"
    PAID_NOT_SHIPPED_ON_TIME = "PAID_NOT_SHIPPED_ON_TIME"
    SHIPPED_WITHOUT_CONFIRMED_PAYMENT = "SHIPPED_WITHOUT_CONFIRMED_PAYMENT"
    DUPLICATE_PAYMENT = "DUPLICATE_PAYMENT"
    SHIPMENT_WITHOUT_TRACKING = "SHIPMENT_WITHOUT_TRACKING"
    CANCELLED_ORDER_SHIPPED = "CANCELLED_ORDER_SHIPPED"
    RETURN_RECEIVED_NOT_REFUNDED = "RETURN_RECEIVED_NOT_REFUNDED"
    REFUND_EXCEEDS_PAYMENT = "REFUND_EXCEEDS_PAYMENT"
    DUPLICATE_REFUND = "DUPLICATE_REFUND"
    CROSS_SYSTEM_RECORD_MISSING = "CROSS_SYSTEM_RECORD_MISSING"


class Severity(StrEnum):
    """Supported anomaly severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewStatus(StrEnum):
    """Supported human review states."""

    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ProblemType(StrEnum):
    """High-level categories used to explain and filter anomalies."""

    FINANCIAL = "financial"
    FULFILLMENT = "fulfillment"
    RETURNS = "returns"
    DATA_QUALITY = "data_quality"


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone.")


@dataclass(frozen=True, slots=True, order=True)
class RecordReference:
    """Identify one source record without retaining the complete row."""

    filename: str
    row_number: int
    record_id: str

    def __post_init__(self) -> None:
        if not self.filename:
            raise ValueError("filename must not be empty.")
        if not isinstance(self.row_number, int) or self.row_number < 1:
            raise ValueError("row_number must be a positive integer.")
        if not self.record_id:
            raise ValueError("record_id must not be empty.")


def deterministic_anomaly_id(
    rule_code: RuleCode,
    references: Sequence[RecordReference],
    *,
    discriminator: str = "",
) -> str:
    """Build a stable anomaly ID from a rule and sorted source references."""

    if not isinstance(rule_code, RuleCode):
        raise TypeError("rule_code must be a RuleCode.")
    ordered_references = sorted(references)
    material = json.dumps(
        {
            "rule_code": rule_code.value,
            "discriminator": discriminator,
            "references": [
                {
                    "filename": reference.filename,
                    "row_number": reference.row_number,
                    "record_id": reference.record_id,
                }
                for reference in ordered_references
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    return f"{rule_code.value.lower()}-{digest}"


@dataclass(frozen=True, slots=True)
class ReconciliationConfig:
    """Central configurable tolerances used by reconciliation rules."""

    monetary_tolerance: Decimal = Decimal("0.01")
    shipping_limit: timedelta = timedelta(hours=48)
    return_refund_limit: timedelta = timedelta(days=7)
    high_shipping_delay_threshold: timedelta | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.monetary_tolerance, Decimal):
            raise TypeError("monetary_tolerance must be a Decimal.")
        if (
            not self.monetary_tolerance.is_finite()
            or self.monetary_tolerance < Decimal("0")
        ):
            raise ValueError("monetary_tolerance must be finite and non-negative.")
        for name in ("shipping_limit", "return_refund_limit"):
            value = getattr(self, name)
            if not isinstance(value, timedelta):
                raise TypeError(f"{name} must be a timedelta.")
            if value <= timedelta(0):
                raise ValueError(f"{name} must be greater than zero.")
        high_threshold = self.high_shipping_delay_threshold
        if high_threshold is not None:
            if not isinstance(high_threshold, timedelta):
                raise TypeError("high_shipping_delay_threshold must be a timedelta or None.")
            if high_threshold <= self.shipping_limit:
                raise ValueError(
                    "high_shipping_delay_threshold must be strictly greater than shipping_limit."
                )


@dataclass(frozen=True, slots=True)
class ReconciliationAnomaly:
    """Represent one deterministic, explainable reconciliation anomaly."""

    anomaly_id: str
    rule_code: RuleCode
    anomaly_code: AnomalyCode
    order_id: str | None
    platform: str
    problem_type: ProblemType
    description: str
    severity: Severity
    detected_at: datetime
    recommended_action: str
    review_status: ReviewStatus = ReviewStatus.OPEN
    compared_values: Mapping[str, str] = field(default_factory=dict)
    record_references: tuple[RecordReference, ...] = ()

    def __post_init__(self) -> None:
        if not self.anomaly_id:
            raise ValueError("anomaly_id must not be empty.")
        if not self.platform:
            raise ValueError("platform must not be empty.")
        if not self.description or not self.recommended_action:
            raise ValueError("description and recommended_action must not be empty.")
        _require_aware_datetime(self.detected_at, "detected_at")
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in self.compared_values.items()):
            raise TypeError("compared_values keys and values must be strings.")
        object.__setattr__(
            self,
            "compared_values",
            MappingProxyType(dict(sorted(self.compared_values.items()))),
        )
        object.__setattr__(
            self,
            "record_references",
            tuple(sorted(self.record_references)),
        )


@dataclass(frozen=True, slots=True)
class RuleNotEvaluated:
    """Explain one rule check that could not produce a reliable conclusion."""

    rule_code: RuleCode
    order_id: str | None
    platform: str
    reason: str
    record_references: tuple[RecordReference, ...] = ()

    def __post_init__(self) -> None:
        if not self.platform or not self.reason:
            raise ValueError("platform and reason must not be empty.")
        object.__setattr__(
            self,
            "record_references",
            tuple(sorted(self.record_references)),
        )


def _protected_counts(values: Sequence[StrEnum]) -> Mapping[StrEnum, int]:
    counts = Counter(values)
    return MappingProxyType(
        {key: counts[key] for key in sorted(counts, key=lambda item: item.value)}
    )


def _anomaly_sort_key(anomaly: ReconciliationAnomaly) -> tuple[object, ...]:
    return (
        anomaly.rule_code.value,
        anomaly.platform,
        anomaly.order_id or "",
        tuple(anomaly.record_references),
        anomaly.anomaly_id,
    )


def _not_evaluated_sort_key(item: RuleNotEvaluated) -> tuple[object, ...]:
    return (
        item.rule_code.value,
        item.platform,
        item.order_id or "",
        tuple(item.record_references),
        item.reason,
    )


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Contain deterministically ordered anomalies and unavailable checks."""

    reference_at: datetime
    config: ReconciliationConfig
    anomalies: tuple[ReconciliationAnomaly, ...] = ()
    not_evaluated: tuple[RuleNotEvaluated, ...] = ()
    _counts_by_code: Mapping[AnomalyCode, int] = field(init=False, repr=False, compare=False)
    _counts_by_severity: Mapping[Severity, int] = field(init=False, repr=False, compare=False)
    _counts_by_platform: Mapping[str, int] = field(init=False, repr=False, compare=False)
    _counts_by_status: Mapping[ReviewStatus, int] = field(init=False, repr=False, compare=False)
    _not_evaluated_counts: Mapping[RuleCode, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_aware_datetime(self.reference_at, "reference_at")
        if not isinstance(self.config, ReconciliationConfig):
            raise TypeError("config must be a ReconciliationConfig.")
        ordered_anomalies = tuple(sorted(self.anomalies, key=_anomaly_sort_key))
        anomaly_ids = tuple(anomaly.anomaly_id for anomaly in ordered_anomalies)
        if len(set(anomaly_ids)) != len(anomaly_ids):
            raise ValueError("ReconciliationResult cannot contain duplicate anomaly IDs.")
        ordered_not_evaluated = tuple(
            sorted(self.not_evaluated, key=_not_evaluated_sort_key)
        )
        object.__setattr__(self, "anomalies", ordered_anomalies)
        object.__setattr__(self, "not_evaluated", ordered_not_evaluated)
        object.__setattr__(
            self,
            "_counts_by_code",
            _protected_counts([item.anomaly_code for item in ordered_anomalies]),
        )
        object.__setattr__(
            self,
            "_counts_by_severity",
            _protected_counts([item.severity for item in ordered_anomalies]),
        )
        platform_counts = Counter(item.platform for item in ordered_anomalies)
        object.__setattr__(
            self,
            "_counts_by_platform",
            MappingProxyType(dict(sorted(platform_counts.items()))),
        )
        object.__setattr__(
            self,
            "_counts_by_status",
            _protected_counts([item.review_status for item in ordered_anomalies]),
        )
        object.__setattr__(
            self,
            "_not_evaluated_counts",
            _protected_counts([item.rule_code for item in ordered_not_evaluated]),
        )

    @property
    def counts_by_code(self) -> Mapping[AnomalyCode, int]:
        return self._counts_by_code

    @property
    def counts_by_severity(self) -> Mapping[Severity, int]:
        return self._counts_by_severity

    @property
    def counts_by_platform(self) -> Mapping[str, int]:
        return self._counts_by_platform

    @property
    def counts_by_status(self) -> Mapping[ReviewStatus, int]:
        return self._counts_by_status

    @property
    def not_evaluated_counts(self) -> Mapping[RuleCode, int]:
        return self._not_evaluated_counts


__all__ = [
    "AnomalyCode",
    "ProblemType",
    "RecordReference",
    "ReconciliationAnomaly",
    "ReconciliationConfig",
    "ReconciliationResult",
    "ReviewStatus",
    "RuleCode",
    "RuleNotEvaluated",
    "Severity",
    "deterministic_anomaly_id",
]
