"""Pure deterministic reconciliation rules REC-06 through REC-10."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from kz_ecomops.validation import ValidationMessage, ValidationStage

from .context import IndexedRecord, ReconciliationContext
from .domain import (
    AnomalyCode,
    ProblemType,
    ReconciliationConfig,
    RuleCode,
    RuleNotEvaluated,
    Severity,
)
from .rules_common import (
    RuleEvaluation,
    decimal_text,
    make_anomaly,
    parse_datetime,
    payment_net,
    validate_rule_inputs,
)


_SHIPPED_STATUSES = frozenset({"shipped", "delivered"})
_RECEIVED_RETURN_STATUSES = frozenset({"received", "completed"})
_RELATIONSHIP_IDENTITY_COLUMNS = frozenset(
    {
        "order_id",
        "payment_id",
        "platform",
        "provider_refund_id",
        "provider_transaction_id",
        "refund_id",
        "return_id",
        "shipment_id",
        "source_order_id",
    }
)


def evaluate_rec_06(
    context: ReconciliationContext,
    reference_at: datetime,
    config: ReconciliationConfig,
) -> RuleEvaluation:
    """Find cancelled orders that still have one or more departed shipments."""

    validate_rule_inputs(context, reference_at, config)
    anomalies = []
    for order_id, order in context.orders_by_id.items():
        if order.get("order_status") != "cancelled":
            continue
        shipments = tuple(
            shipment
            for shipment in context.for_order("shipments.csv", order_id)
            if shipment.get("shipment_status") in _SHIPPED_STATUSES
        )
        if not shipments:
            continue
        anomalies.append(
            make_anomaly(
                rule_code=RuleCode.REC_06,
                anomaly_code=AnomalyCode.CANCELLED_ORDER_SHIPPED,
                order_id=order_id,
                platform=order.get("platform"),
                problem_type=ProblemType.FULFILLMENT,
                description="The cancelled order still has a shipped or delivered shipment.",
                severity=Severity.CRITICAL,
                reference_at=reference_at,
                recommended_action=(
                    "Check whether delivery can be stopped and review payment and refund status."
                ),
                compared_values={
                    "order_status": order.get("order_status"),
                    "shipped_record_count": str(len(shipments)),
                },
                records=(order, *shipments),
            )
        )
    return RuleEvaluation(anomalies=tuple(anomalies))


def _associated_refunds(
    context: ReconciliationContext,
    returned_item: IndexedRecord,
    all_returns: tuple[IndexedRecord, ...],
) -> tuple[tuple[IndexedRecord, ...], tuple[IndexedRecord, ...]]:
    succeeded = tuple(
        refund
        for refund in context.for_order("refunds.csv", returned_item.get("order_id"))
        if refund.get("refund_status") == "succeeded"
    )
    direct = tuple(
        refund
        for refund in succeeded
        if refund.get("return_id") == returned_item.get("return_id")
    )
    unlinked = tuple(refund for refund in succeeded if not refund.get("return_id").strip())
    if len(all_returns) == 1:
        return tuple(sorted((*direct, *unlinked), key=lambda item: item.reference)), ()
    if direct:
        return tuple(sorted(direct, key=lambda item: item.reference)), ()
    if unlinked:
        return (), tuple((*all_returns, *unlinked))
    return (), ()


def _rec07_anomaly(
    *,
    returned_item: IndexedRecord,
    order: IndexedRecord | None,
    refunds: tuple[IndexedRecord, ...],
    reference_at: datetime,
    config: ReconciliationConfig,
    actual_refund: Decimal,
    expected_refund: Decimal | None,
) -> object:
    records = ((order,) if order is not None else ()) + (returned_item, *refunds)
    compared_values = {
        "confirmed_refund": decimal_text(actual_refund),
        "received_at": returned_item.get("received_at"),
        "reference_at": reference_at.isoformat(),
        "refund_limit_seconds": str(int(config.return_refund_limit.total_seconds())),
    }
    if expected_refund is not None:
        compared_values["expected_refund"] = decimal_text(expected_refund)
    return make_anomaly(
        rule_code=RuleCode.REC_07,
        anomaly_code=AnomalyCode.RETURN_RECEIVED_NOT_REFUNDED,
        order_id=returned_item.get("order_id"),
        platform=returned_item.get("platform"),
        problem_type=ProblemType.RETURNS,
        description="The received return has no sufficient confirmed refund after the configured limit.",
        severity=Severity.HIGH,
        reference_at=reference_at,
        recommended_action=(
            "Review the return inspection and complete or document the expected refund."
        ),
        compared_values=compared_values,
        records=records,
        discriminator=returned_item.get("return_id"),
    )


def evaluate_rec_07(
    context: ReconciliationContext,
    reference_at: datetime,
    config: ReconciliationConfig,
) -> RuleEvaluation:
    """Find overdue received returns without a verifiably sufficient refund."""

    validate_rule_inputs(context, reference_at, config)
    anomalies = []
    not_evaluated = []
    received_by_order: dict[str, list[IndexedRecord]] = defaultdict(list)
    for returned_item in context.records_by_file["returns.csv"]:
        if returned_item.get("return_status") in _RECEIVED_RETURN_STATUSES:
            received_by_order[returned_item.get("order_id")].append(returned_item)

    for order_id in sorted(received_by_order):
        received_returns = tuple(received_by_order[order_id])
        all_returns = context.for_order("returns.csv", order_id)
        for returned_item in received_returns:
            received_at = parse_datetime(returned_item.get("received_at"))
            if reference_at - received_at <= config.return_refund_limit:
                continue
            refunds, ambiguity_records = _associated_refunds(
                context, returned_item, all_returns
            )
            order = context.orders_by_id.get(order_id)
            if ambiguity_records:
                records = ((order,) if order is not None else ()) + ambiguity_records
                unique_records = {record.reference: record for record in records}
                not_evaluated.append(
                    RuleNotEvaluated(
                        rule_code=RuleCode.REC_07,
                        order_id=order_id,
                        platform=returned_item.get("platform"),
                        reason=(
                            "A confirmed refund without return_id cannot be assigned "
                            "unambiguously because the order has multiple returns."
                        ),
                        record_references=tuple(unique_records),
                    )
                )
                continue

            expected_text = returned_item.get("expected_refund_amount").strip()
            currency = returned_item.get("currency")
            same_currency_refunds = tuple(
                refund for refund in refunds if not currency or refund.get("currency") == currency
            )
            actual_refund = sum(
                (Decimal(refund.get("amount")) for refund in same_currency_refunds),
                Decimal("0"),
            )
            if not expected_text:
                if same_currency_refunds:
                    records = ((order,) if order is not None else ()) + (
                        returned_item,
                        *same_currency_refunds,
                    )
                    not_evaluated.append(
                        RuleNotEvaluated(
                            rule_code=RuleCode.REC_07,
                            order_id=order_id,
                            platform=returned_item.get("platform"),
                            reason=(
                                "A confirmed partial refund exists, but expected_refund_amount "
                                "is unavailable, so sufficiency cannot be verified."
                            ),
                            record_references=tuple(record.reference for record in records),
                        )
                    )
                    continue
                anomalies.append(
                    _rec07_anomaly(
                        returned_item=returned_item,
                        order=order,
                        refunds=(),
                        reference_at=reference_at,
                        config=config,
                        actual_refund=actual_refund,
                        expected_refund=None,
                    )
                )
                continue

            expected_refund = Decimal(expected_text)
            shortfall = expected_refund - actual_refund
            if shortfall <= config.monetary_tolerance:
                continue
            anomalies.append(
                _rec07_anomaly(
                    returned_item=returned_item,
                    order=order,
                    refunds=same_currency_refunds,
                    reference_at=reference_at,
                    config=config,
                    actual_refund=actual_refund,
                    expected_refund=expected_refund,
                )
            )
    return RuleEvaluation(
        anomalies=tuple(anomalies),
        not_evaluated=tuple(not_evaluated),
    )


def evaluate_rec_08(
    context: ReconciliationContext,
    reference_at: datetime,
    config: ReconciliationConfig,
) -> RuleEvaluation:
    """Find same-currency succeeded refunds exceeding confirmed net payments."""

    validate_rule_inputs(context, reference_at, config)
    anomalies = []
    for order_id, order in context.orders_by_id.items():
        currency = order.get("currency")
        refunds = tuple(
            refund
            for refund in context.for_order("refunds.csv", order_id)
            if refund.get("refund_status") == "succeeded"
            and refund.get("currency") == currency
        )
        if not refunds:
            continue
        refund_total = sum(
            (Decimal(refund.get("amount")) for refund in refunds), Decimal("0")
        )
        net_paid, payments = payment_net(context, order)
        excess = refund_total - net_paid
        if excess <= config.monetary_tolerance:
            continue
        anomalies.append(
            make_anomaly(
                rule_code=RuleCode.REC_08,
                anomaly_code=AnomalyCode.REFUND_EXCEEDS_PAYMENT,
                order_id=order_id,
                platform=order.get("platform"),
                problem_type=ProblemType.FINANCIAL,
                description="Confirmed refunds exceed confirmed net payments.",
                severity=Severity.CRITICAL,
                reference_at=reference_at,
                recommended_action=(
                    "Stop further refunds and immediately verify every order transaction."
                ),
                compared_values={
                    "confirmed_refund": decimal_text(refund_total),
                    "currency": currency,
                    "excess": decimal_text(excess),
                    "net_confirmed_payment": decimal_text(net_paid),
                },
                records=(order, *payments, *refunds),
            )
        )
    return RuleEvaluation(anomalies=tuple(anomalies))


def _duplicate_refund_groups(
    refunds: tuple[IndexedRecord, ...],
) -> tuple[tuple[IndexedRecord, ...], ...]:
    parents = list(range(len(refunds)))

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

    by_refund_id: dict[str, list[int]] = defaultdict(list)
    by_provider: dict[tuple[str, str], list[int]] = defaultdict(list)
    for position, refund in enumerate(refunds):
        by_refund_id[refund.get("refund_id")].append(position)
        provider_id = refund.get("provider_refund_id").strip()
        if provider_id:
            by_provider[(refund.get("platform"), provider_id)].append(position)
    for positions in (*by_refund_id.values(), *by_provider.values()):
        for position in positions[1:]:
            union(positions[0], position)

    groups: dict[int, list[IndexedRecord]] = defaultdict(list)
    for position, refund in enumerate(refunds):
        groups[find(position)].append(refund)
    return tuple(
        tuple(sorted(group, key=lambda item: item.reference))
        for group in groups.values()
        if len(group) > 1
    )


def evaluate_rec_09(
    context: ReconciliationContext,
    reference_at: datetime,
    config: ReconciliationConfig,
) -> RuleEvaluation:
    """Find duplicate refund groups without duplicate overlapping anomalies."""

    validate_rule_inputs(context, reference_at, config)
    anomalies = []
    for group in _duplicate_refund_groups(context.records_by_file["refunds.csv"]):
        order_ids = sorted({item.get("order_id") for item in group})
        platforms = sorted({item.get("platform") for item in group})
        order_id = order_ids[0] if len(order_ids) == 1 else None
        platform = platforms[0] if len(platforms) == 1 else "multiple"
        order = context.orders_by_id.get(order_id or "")
        records = ((order,) if order is not None else ()) + group
        anomalies.append(
            make_anomaly(
                rule_code=RuleCode.REC_09,
                anomaly_code=AnomalyCode.DUPLICATE_REFUND,
                order_id=order_id,
                platform=platform,
                problem_type=ProblemType.FINANCIAL,
                description="Multiple refund records share a refund or provider refund identifier.",
                severity=Severity.CRITICAL,
                reference_at=reference_at,
                recommended_action=(
                    "Verify provider movements and prevent any further duplicate credit."
                ),
                compared_values={
                    "duplicate_record_count": str(len(group)),
                    "provider_refund_ids": ",".join(
                        sorted(
                            {
                                item.get("provider_refund_id")
                                for item in group
                                if item.get("provider_refund_id").strip()
                            }
                        )
                    ),
                    "refund_ids": ",".join(sorted({item.get("refund_id") for item in group})),
                },
                records=records,
                discriminator="|".join(order_ids),
            )
        )
    return RuleEvaluation(anomalies=tuple(anomalies))


def _relationship_records(
    context: ReconciliationContext,
    message: ValidationMessage,
) -> tuple[IndexedRecord, ...]:
    row_number = message.row_numbers[0]
    affected = context.records_by_file[message.filename][row_number - 1]
    records: list[IndexedRecord] = [affected]
    order = context.orders_by_id.get(affected.get("order_id"))
    if order is not None:
        records.append(order)
    if message.code.startswith("return_reference"):
        returned_item = context.returns_by_id.get(affected.get("return_id"))
        if returned_item is not None:
            records.append(returned_item)
    if message.code.startswith("payment_reference"):
        records.extend(context.payments_by_id.get(affected.get("payment_id"), ()))
    unique_records = {record.reference: record for record in records}
    return tuple(unique_records[reference] for reference in sorted(unique_records))


def _relationship_severity(message: ValidationMessage) -> Severity:
    financial_file = message.filename in {"payments.csv", "refunds.csv"}
    financial_reference = message.code.startswith(("payment_reference", "return_reference"))
    return Severity.CRITICAL if financial_file or financial_reference else Severity.HIGH


def _relationship_discriminator(
    message: ValidationMessage,
    affected: IndexedRecord,
) -> str:
    """Identify one relationship problem from stable business values."""

    columns = sorted(_RELATIONSHIP_IDENTITY_COLUMNS.union(message.columns))
    business_values = {
        column: affected.get(column)
        for column in columns
        if column in affected.values
    }
    return json.dumps(
        {
            "business_values": business_values,
            "finding_code": message.code,
            "source_file": message.filename,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _state_missing_anomaly(
    *,
    context: ReconciliationContext,
    order: IndexedRecord,
    reference_at: datetime,
    event: str,
    severity: Severity,
    state_column: str,
) -> object:
    action = "Check export completeness, identifier mapping, and system synchronization."
    return make_anomaly(
        rule_code=RuleCode.REC_10,
        anomaly_code=AnomalyCode.CROSS_SYSTEM_RECORD_MISSING,
        order_id=order.get("order_id"),
        platform=order.get("platform"),
        problem_type=ProblemType.DATA_QUALITY,
        description=f"The order state declares {event}, but no matching detail record exists.",
        severity=severity,
        reference_at=reference_at,
        recommended_action=action,
        compared_values={
            "declared_event": event,
            "declared_state": order.get(state_column),
            "state_column": state_column,
        },
        records=(order,),
        discriminator=event,
    )


def evaluate_rec_10(
    context: ReconciliationContext,
    relationship_messages: tuple[ValidationMessage, ...],
    reference_at: datetime,
    config: ReconciliationConfig,
) -> RuleEvaluation:
    """Convert relationship findings and missing declared events into anomalies."""

    validate_rule_inputs(context, reference_at, config)
    anomalies = []
    for message in relationship_messages:
        if message.stage is not ValidationStage.RELATIONSHIP or message.blocking:
            continue
        affected = context.records_by_file[message.filename][message.row_numbers[0] - 1]
        records = _relationship_records(context, message)
        anomalies.append(
            make_anomaly(
                rule_code=RuleCode.REC_10,
                anomaly_code=AnomalyCode.CROSS_SYSTEM_RECORD_MISSING,
                order_id=affected.get("order_id") or None,
                platform=affected.get("platform"),
                problem_type=ProblemType.DATA_QUALITY,
                description="A cross-file relationship is missing or inconsistent.",
                severity=_relationship_severity(message),
                reference_at=reference_at,
                recommended_action=(
                    "Check export completeness, identifier mapping, and system synchronization."
                ),
                compared_values={
                    "columns": ",".join(message.columns),
                    "finding_code": message.code,
                    "source_file": message.filename,
                    "source_row_number": str(message.row_numbers[0]),
                },
                records=records,
                discriminator=_relationship_discriminator(message, affected),
            )
        )

    for order_id, order in context.orders_by_id.items():
        payments = context.for_order("payments.csv", order_id)
        shipments = context.for_order("shipments.csv", order_id)
        returns = context.for_order("returns.csv", order_id)
        refunds = context.for_order("refunds.csv", order_id)
        if order.get("payment_status") in {"paid", "partially_refunded", "refunded"} and not any(
            item.get("payment_status") == "succeeded" for item in payments
        ):
            anomalies.append(
                _state_missing_anomaly(
                    context=context,
                    order=order,
                    reference_at=reference_at,
                    event="a completed payment",
                    severity=Severity.CRITICAL,
                    state_column="payment_status",
                )
            )
        if order.get("fulfillment_status") == "fulfilled" and not any(
            item.get("shipment_status") in _SHIPPED_STATUSES for item in shipments
        ):
            anomalies.append(
                _state_missing_anomaly(
                    context=context,
                    order=order,
                    reference_at=reference_at,
                    event="completed fulfillment",
                    severity=Severity.HIGH,
                    state_column="fulfillment_status",
                )
            )
        if order.get("fulfillment_status") == "returned" and not returns:
            anomalies.append(
                _state_missing_anomaly(
                    context=context,
                    order=order,
                    reference_at=reference_at,
                    event="a return",
                    severity=Severity.HIGH,
                    state_column="fulfillment_status",
                )
            )
        if order.get("payment_status") in {"partially_refunded", "refunded"} and not any(
            item.get("refund_status") == "succeeded" for item in refunds
        ):
            anomalies.append(
                _state_missing_anomaly(
                    context=context,
                    order=order,
                    reference_at=reference_at,
                    event="a confirmed refund",
                    severity=Severity.CRITICAL,
                    state_column="payment_status",
                )
            )
    return RuleEvaluation(anomalies=tuple(anomalies))


__all__ = [
    "evaluate_rec_06",
    "evaluate_rec_07",
    "evaluate_rec_08",
    "evaluate_rec_09",
    "evaluate_rec_10",
]
