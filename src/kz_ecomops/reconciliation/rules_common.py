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
    """Return the latest succeeded timestamp that restores full net payment."""

    target = Decimal(order.get("order_total")) - tolerance
    accumulated = Decimal("0")
    events: list[tuple[datetime, int, str, IndexedRecord]] = []

    for payment in usable_payments:
        status = payment.get("payment_status")
        if status == "succeeded" and payment.get("paid_at"):
            event_at = parse_datetime(payment.get("paid_at"))
            events.append((event_at, 0, payment.reference.record_id, payment))
            continue
        if status == "reversed":
            event_text = payment.get("updated_at") or payment.get("created_at")
            if event_text:
                event_at = parse_datetime(event_text)
                events.append((event_at, 1, payment.reference.record_id, payment))
            else:
                # Validated exports always provide an event timestamp. Keeping an
                # undated reversal in the opening balance is the conservative
                # fallback for direct callers of this helper.
                accumulated -= Decimal(payment.get("amount"))

    completed_at = None
    for event_at, _, _, payment in sorted(events, key=lambda item: item[:3]):
        if payment.get("payment_status") == "succeeded":
            accumulated += Decimal(payment.get("amount"))
            if accumulated >= target and completed_at is None:
                completed_at = event_at
        else:
            accumulated -= Decimal(payment.get("amount"))
            if accumulated < target:
                completed_at = None
    return completed_at


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
