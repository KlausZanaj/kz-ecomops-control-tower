"""Shared deterministic helpers for pure reconciliation rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .context import IndexedRecord, ReconciliationContext
from .domain import (
    AnomalyCode,
    ProblemType,
    ReconciliationAnomaly,
    ReconciliationConfig,
    RuleCode,
    RuleNotEvaluated,
    Severity,
    deterministic_anomaly_id,
)


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    """Internal immutable output returned by every pure rule."""

    anomalies: tuple[ReconciliationAnomaly, ...] = ()
    not_evaluated: tuple[RuleNotEvaluated, ...] = ()


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def payment_net(
    context: ReconciliationContext,
    order: IndexedRecord,
) -> tuple[Decimal, tuple[IndexedRecord, ...]]:
    """Return same-currency succeeded payments minus reversals for one order."""

    currency = order.get("currency")
    total = Decimal("0")
    usable: list[IndexedRecord] = []
    for payment in context.for_order("payments.csv", order.get("order_id")):
        if payment.get("currency") != currency:
            continue
        status = payment.get("payment_status")
        if status == "succeeded":
            total += Decimal(payment.get("amount"))
            usable.append(payment)
        elif status == "reversed":
            total -= Decimal(payment.get("amount"))
            usable.append(payment)
    return total, tuple(usable)


def completed_payment_at(
    order: IndexedRecord,
    usable_payments: tuple[IndexedRecord, ...],
    tolerance: Decimal,
) -> datetime | None:
    """Return the succeeded timestamp at which the order first became fully paid."""

    target = Decimal(order.get("order_total")) - tolerance
    succeeded = sorted(
        (
            payment
            for payment in usable_payments
            if payment.get("payment_status") == "succeeded" and payment.get("paid_at")
        ),
        key=lambda payment: (
            parse_datetime(payment.get("paid_at")),
            payment.reference,
        ),
    )
    accumulated = Decimal("0")
    for payment in succeeded:
        accumulated += Decimal(payment.get("amount"))
        if accumulated >= target:
            return parse_datetime(payment.get("paid_at"))
    return None


def make_anomaly(
    *,
    rule_code: RuleCode,
    anomaly_code: AnomalyCode,
    order_id: str | None,
    platform: str,
    problem_type: ProblemType,
    description: str,
    severity: Severity,
    reference_at: datetime,
    recommended_action: str,
    compared_values: dict[str, str],
    records: tuple[IndexedRecord, ...],
    discriminator: str = "",
) -> ReconciliationAnomaly:
    references = tuple(record.reference for record in records)
    return ReconciliationAnomaly(
        anomaly_id=deterministic_anomaly_id(
            rule_code,
            references,
            discriminator=discriminator or order_id or "",
        ),
        rule_code=rule_code,
        anomaly_code=anomaly_code,
        order_id=order_id,
        platform=platform,
        problem_type=problem_type,
        description=description,
        severity=severity,
        detected_at=reference_at,
        recommended_action=recommended_action,
        compared_values=compared_values,
        record_references=references,
    )


def validate_rule_inputs(
    context: ReconciliationContext,
    reference_at: datetime,
    config: ReconciliationConfig,
) -> None:
    if not isinstance(context, ReconciliationContext):
        raise TypeError("context must be a ReconciliationContext.")
    if reference_at.tzinfo is None or reference_at.utcoffset() is None:
        raise ValueError("reference_at must include a timezone.")
    if not isinstance(config, ReconciliationConfig):
        raise TypeError("config must be a ReconciliationConfig.")
