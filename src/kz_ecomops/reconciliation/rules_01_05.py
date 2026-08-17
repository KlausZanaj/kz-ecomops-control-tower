"""Pure deterministic reconciliation rules REC-01 through REC-05."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from .context import IndexedRecord, ReconciliationContext
from .domain import (
    AnomalyCode,
    ProblemType,
    ReconciliationConfig,
    RuleCode,
    Severity,
)
from .rules_common import (
    RuleEvaluation,
    completed_payment_at,
    decimal_text,
    make_anomaly,
    payment_net,
    validate_rule_inputs,
)


_DECLARED_PAYMENT_STATUSES = frozenset(
    {"partially_paid", "paid", "partially_refunded", "refunded"}
)
_SHIPPED_STATUSES = frozenset({"shipped", "delivered"})


def evaluate_rec_01(
    context: ReconciliationContext,
    reference_at: datetime,
    config: ReconciliationConfig,
) -> RuleEvaluation:
    """Find declared paid orders whose usable net payment differs from total."""

    validate_rule_inputs(context, reference_at, config)
    anomalies = []
    for order_id, order in context.orders_by_id.items():
        if order.get("payment_status") not in _DECLARED_PAYMENT_STATUSES:
            continue
        net_paid, usable = payment_net(context, order)
        if not usable:
            continue
        order_total = Decimal(order.get("order_total"))
        difference = abs(net_paid - order_total)
        if difference <= config.monetary_tolerance:
            continue
        anomalies.append(
            make_anomaly(
                rule_code=RuleCode.REC_01,
                anomaly_code=AnomalyCode.PAYMENT_AMOUNT_MISMATCH,
                order_id=order_id,
                platform=order.get("platform"),
                problem_type=ProblemType.FINANCIAL,
                description="Confirmed net payments do not match the order total.",
                severity=Severity.HIGH,
                reference_at=reference_at,
                recommended_action=(
                    "Compare the order transactions in the sales channel and payment provider."
                ),
                compared_values={
                    "currency": order.get("currency"),
                    "difference": decimal_text(difference),
                    "net_confirmed_payment": decimal_text(net_paid),
                    "order_total": decimal_text(order_total),
                },
                records=(order, *usable),
            )
        )
    return RuleEvaluation(anomalies=tuple(anomalies))


def evaluate_rec_02(
    context: ReconciliationContext,
    reference_at: datetime,
    config: ReconciliationConfig,
) -> RuleEvaluation:
    """Find fully paid non-cancelled orders shipped after the calendar limit."""

    validate_rule_inputs(context, reference_at, config)
    anomalies = []
    for order_id, order in context.orders_by_id.items():
        if order.get("order_status") == "cancelled":
            continue
        shipments = context.for_order("shipments.csv", order_id)
        if any(item.get("shipment_status") in _SHIPPED_STATUSES for item in shipments):
            continue
        net_paid, usable = payment_net(context, order)
        order_total = Decimal(order.get("order_total"))
        if net_paid < order_total - config.monetary_tolerance:
            continue
        paid_at = completed_payment_at(order, usable, config.monetary_tolerance)
        if paid_at is None:
            continue
        delay = reference_at - paid_at
        if delay <= config.shipping_limit:
            continue
        severity = Severity.MEDIUM
        if (
            config.high_shipping_delay_threshold is not None
            and delay > config.high_shipping_delay_threshold
        ):
            severity = Severity.HIGH
        anomalies.append(
            make_anomaly(
                rule_code=RuleCode.REC_02,
                anomaly_code=AnomalyCode.PAID_NOT_SHIPPED_ON_TIME,
                order_id=order_id,
                platform=order.get("platform"),
                problem_type=ProblemType.FULFILLMENT,
                description="The fully paid order has not shipped within the configured limit.",
                severity=severity,
                reference_at=reference_at,
                recommended_action=(
                    "Check inventory availability, warehouse blocks, and fulfillment status."
                ),
                compared_values={
                    "paid_at": paid_at.isoformat(),
                    "reference_at": reference_at.isoformat(),
                    "shipping_limit_seconds": str(int(config.shipping_limit.total_seconds())),
                },
                records=(order, *usable, *shipments),
            )
        )
    return RuleEvaluation(anomalies=tuple(anomalies))


def evaluate_rec_03(
    context: ReconciliationContext,
    reference_at: datetime,
    config: ReconciliationConfig,
) -> RuleEvaluation:
    """Find shipped orders whose confirmed net payment is insufficient."""

    validate_rule_inputs(context, reference_at, config)
    anomalies = []
    for order_id, order in context.orders_by_id.items():
        shipments = tuple(
            item
            for item in context.for_order("shipments.csv", order_id)
            if item.get("shipment_status") in _SHIPPED_STATUSES
        )
        if not shipments:
            continue
        net_paid, usable = payment_net(context, order)
        order_total = Decimal(order.get("order_total"))
        shortfall = order_total - net_paid
        if shortfall <= config.monetary_tolerance:
            continue
        anomalies.append(
            make_anomaly(
                rule_code=RuleCode.REC_03,
                anomaly_code=AnomalyCode.SHIPPED_WITHOUT_CONFIRMED_PAYMENT,
                order_id=order_id,
                platform=order.get("platform"),
                problem_type=ProblemType.FINANCIAL,
                description="The order shipped without sufficient confirmed net payment.",
                severity=Severity.CRITICAL,
                reference_at=reference_at,
                recommended_action=(
                    "Immediately verify the payment method and recover the unpaid amount."
                ),
                compared_values={
                    "currency": order.get("currency"),
                    "net_confirmed_payment": decimal_text(net_paid),
                    "order_total": decimal_text(order_total),
                    "shortfall": decimal_text(shortfall),
                },
                records=(order, *usable, *shipments),
            )
        )
    return RuleEvaluation(anomalies=tuple(anomalies))


def _duplicate_payment_groups(
    payments: tuple[IndexedRecord, ...],
) -> tuple[tuple[IndexedRecord, ...], ...]:
    parents = list(range(len(payments)))

    def find(position: int) -> int:
        while parents[position] != position:
            parents[position] = parents[parents[position]]
            position = parents[position]
        return position

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parents[max(first_root, second_root)] = min(first_root, second_root)

    by_payment_id: dict[str, list[int]] = defaultdict(list)
    by_provider: dict[tuple[str, str], list[int]] = defaultdict(list)
    for position, payment in enumerate(payments):
        by_payment_id[payment.get("payment_id")].append(position)
        provider_id = payment.get("provider_transaction_id").strip()
        if provider_id:
            by_provider[(payment.get("platform"), provider_id)].append(position)
    for positions in (*by_payment_id.values(), *by_provider.values()):
        for position in positions[1:]:
            union(positions[0], position)

    groups: dict[int, list[IndexedRecord]] = defaultdict(list)
    for position, payment in enumerate(payments):
        groups[find(position)].append(payment)
    return tuple(
        tuple(sorted(group, key=lambda item: item.reference))
        for group in groups.values()
        if len(group) > 1
    )


def evaluate_rec_04(
    context: ReconciliationContext,
    reference_at: datetime,
    config: ReconciliationConfig,
) -> RuleEvaluation:
    """Find duplicate payment groups without double-reporting overlapping keys."""

    validate_rule_inputs(context, reference_at, config)
    payments = context.records_by_file["payments.csv"]
    anomalies = []
    for group in _duplicate_payment_groups(payments):
        order_ids = sorted({item.get("order_id") for item in group})
        platforms = sorted({item.get("platform") for item in group})
        order_id = order_ids[0] if len(order_ids) == 1 else None
        platform = platforms[0] if len(platforms) == 1 else "multiple"
        order = context.orders_by_id.get(order_id or "")
        records = ((order,) if order is not None else ()) + group
        anomalies.append(
            make_anomaly(
                rule_code=RuleCode.REC_04,
                anomaly_code=AnomalyCode.DUPLICATE_PAYMENT,
                order_id=order_id,
                platform=platform,
                problem_type=ProblemType.FINANCIAL,
                description="Multiple payment records share a payment or provider transaction identifier.",
                severity=Severity.HIGH,
                reference_at=reference_at,
                recommended_action=(
                    "Verify the provider transactions before issuing any duplicate-charge refund."
                ),
                compared_values={
                    "duplicate_record_count": str(len(group)),
                    "payment_ids": ",".join(sorted({item.get("payment_id") for item in group})),
                    "provider_transaction_ids": ",".join(
                        sorted(
                            {
                                item.get("provider_transaction_id")
                                for item in group
                                if item.get("provider_transaction_id").strip()
                            }
                        )
                    ),
                },
                records=records,
                discriminator="|".join(order_ids),
            )
        )
    return RuleEvaluation(anomalies=tuple(anomalies))


def evaluate_rec_05(
    context: ReconciliationContext,
    reference_at: datetime,
    config: ReconciliationConfig,
) -> RuleEvaluation:
    """Find every shipped or delivered record with a blank tracking number."""

    validate_rule_inputs(context, reference_at, config)
    anomalies = []
    for shipment in context.records_by_file["shipments.csv"]:
        if shipment.get("shipment_status") not in _SHIPPED_STATUSES:
            continue
        if shipment.get("tracking_number").strip():
            continue
        order_id = shipment.get("order_id")
        order = context.orders_by_id.get(order_id)
        records = ((order,) if order is not None else ()) + (shipment,)
        anomalies.append(
            make_anomaly(
                rule_code=RuleCode.REC_05,
                anomaly_code=AnomalyCode.SHIPMENT_WITHOUT_TRACKING,
                order_id=order_id,
                platform=shipment.get("platform"),
                problem_type=ProblemType.FULFILLMENT,
                description="A shipped or delivered shipment has no tracking number.",
                severity=Severity.MEDIUM,
                reference_at=reference_at,
                recommended_action=(
                    "Retrieve the tracking number from the carrier and update the sales channel."
                ),
                compared_values={
                    "shipment_id": shipment.get("shipment_id"),
                    "shipment_status": shipment.get("shipment_status"),
                    "tracking_number": shipment.get("tracking_number"),
                },
                records=records,
                discriminator=shipment.get("shipment_id"),
            )
        )
    return RuleEvaluation(anomalies=tuple(anomalies))


__all__ = [
    "evaluate_rec_01",
    "evaluate_rec_02",
    "evaluate_rec_03",
    "evaluate_rec_04",
    "evaluate_rec_05",
]
