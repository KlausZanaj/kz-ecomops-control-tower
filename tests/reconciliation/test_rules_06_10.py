"""Rule-level tests for deterministic REC-06 through REC-10 checks."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from kz_ecomops.reconciliation import (
    AnomalyCode,
    ReconciliationConfig,
    RuleCode,
    Severity,
    evaluate_rec_06,
    evaluate_rec_07,
    evaluate_rec_08,
    evaluate_rec_09,
    evaluate_rec_10,
)
from kz_ecomops.reconciliation.context import ReconciliationContext
from kz_ecomops.validation import CSV_SCHEMAS, validate_dataset_directory


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = PROJECT_ROOT / "data" / "sample"
REFERENCE_AT = datetime(2026, 3, 20, 12, tzinfo=timezone.utc)


def _row(filename: str, **values: str) -> dict[str, str]:
    row = {column: "" for column in CSV_SCHEMAS[filename].column_names}
    row.update(values)
    return row


def _order(
    *,
    order_status: str = "confirmed",
    payment_status: str = "paid",
    fulfillment_status: str = "fulfilled",
) -> dict[str, str]:
    return _row(
        "orders.csv",
        order_id="shopify:ORDER-1",
        platform="shopify",
        source_order_id="ORDER-1",
        order_status=order_status,
        payment_status=payment_status,
        fulfillment_status=fulfillment_status,
        currency="EUR",
        order_total="100.00",
    )


def _payment(payment_id: str = "PAY-1", amount: str = "100.00", *, status: str = "succeeded") -> dict[str, str]:
    return _row(
        "payments.csv",
        payment_id=payment_id,
        platform="shopify",
        order_id="shopify:ORDER-1",
        source_order_id="ORDER-1",
        provider_transaction_id=f"TXN-{payment_id}",
        payment_status=status,
        amount=amount,
        currency="EUR",
        paid_at="2026-03-01T10:00:00+00:00" if status == "succeeded" else "",
    )


def _shipment(shipment_id: str = "SHIP-1", *, status: str = "shipped") -> dict[str, str]:
    return _row(
        "shipments.csv",
        shipment_id=shipment_id,
        platform="shopify",
        order_id="shopify:ORDER-1",
        source_order_id="ORDER-1",
        shipment_status=status,
        tracking_number="TRACK-1",
        shipped_at="2026-03-02T10:00:00+00:00" if status in {"shipped", "delivered"} else "",
        delivered_at="2026-03-03T10:00:00+00:00" if status == "delivered" else "",
    )


def _return(
    return_id: str = "RETURN-1",
    *,
    expected: str = "100.00",
    received_at: str = "2026-03-10T12:00:00+00:00",
    status: str = "received",
) -> dict[str, str]:
    return _row(
        "returns.csv",
        return_id=return_id,
        platform="shopify",
        order_id="shopify:ORDER-1",
        source_order_id="ORDER-1",
        return_status=status,
        received_at=received_at if status in {"received", "completed"} else "",
        expected_refund_amount=expected,
        currency="EUR" if expected else "",
    )


def _refund(
    refund_id: str = "REFUND-1",
    amount: str = "100.00",
    *,
    status: str = "succeeded",
    return_id: str = "RETURN-1",
    provider_id: str | None = None,
) -> dict[str, str]:
    return _row(
        "refunds.csv",
        refund_id=refund_id,
        platform="shopify",
        order_id="shopify:ORDER-1",
        source_order_id="ORDER-1",
        return_id=return_id,
        payment_id="PAY-1",
        provider_refund_id=provider_id if provider_id is not None else f"PROVIDER-{refund_id}",
        refund_status=status,
        amount=amount,
        currency="EUR",
        refunded_at="2026-03-18T10:00:00+00:00" if status == "succeeded" else "",
    )


def _context(
    *,
    orders: tuple[dict[str, str], ...] | None = None,
    payments: tuple[dict[str, str], ...] = (),
    shipments: tuple[dict[str, str], ...] = (),
    returns: tuple[dict[str, str], ...] = (),
    refunds: tuple[dict[str, str], ...] = (),
) -> tuple[ReconciliationContext, dict[str, pd.DataFrame]]:
    rows = {
        "orders.csv": orders if orders is not None else (_order(),),
        "payments.csv": payments,
        "shipments.csv": shipments,
        "returns.csv": returns,
        "refunds.csv": refunds,
    }
    frames = {
        filename: pd.DataFrame(data, columns=CSV_SCHEMAS[filename].column_names, dtype=str)
        for filename, data in rows.items()
    }
    return ReconciliationContext.from_dataframes(frames), frames


def test_rec06_positive_negative_and_multiple_shipments() -> None:
    cancelled, _ = _context(
        orders=(_order(order_status="cancelled"),),
        shipments=(_shipment("SHIP-1"), _shipment("SHIP-2", status="delivered")),
    )
    pending, _ = _context(
        orders=(_order(order_status="cancelled"),),
        shipments=(_shipment(status="pending"),),
    )
    active, _ = _context(shipments=(_shipment(),))
    anomalies = evaluate_rec_06(cancelled, REFERENCE_AT, ReconciliationConfig()).anomalies
    assert len(anomalies) == 1
    assert len(anomalies[0].record_references) == 3
    assert not evaluate_rec_06(pending, REFERENCE_AT, ReconciliationConfig()).anomalies
    assert not evaluate_rec_06(active, REFERENCE_AT, ReconciliationConfig()).anomalies


def test_rec07_time_boundary_missing_and_sufficient_refund() -> None:
    returned = _return(received_at="2026-03-10T12:00:00+00:00")
    no_refund, _ = _context(returns=(returned,))
    sufficient, _ = _context(returns=(returned,), refunds=(_refund(),))
    boundary = datetime(2026, 3, 17, 12, tzinfo=timezone.utc)
    assert not evaluate_rec_07(no_refund, boundary, ReconciliationConfig()).anomalies
    assert len(
        evaluate_rec_07(no_refund, boundary + timedelta(seconds=1), ReconciliationConfig()).anomalies
    ) == 1
    assert not evaluate_rec_07(sufficient, REFERENCE_AT, ReconciliationConfig()).anomalies


def test_rec07_aggregate_boundary_failed_refunds_and_not_evaluated() -> None:
    returned = _return(expected="100.00")
    boundary_refund, _ = _context(
        returns=(returned,),
        refunds=(
            _refund("REFUND-1", "60.00"),
            _refund("REFUND-2", "39.99"),
            _refund("REFUND-3", "500.00", status="failed"),
        ),
    )
    insufficient, _ = _context(returns=(returned,), refunds=(_refund(amount="90.00"),))
    unknown_expected, _ = _context(
        returns=(_return(expected=""),),
        refunds=(_refund(amount="25.00"),),
    )
    assert not evaluate_rec_07(boundary_refund, REFERENCE_AT, ReconciliationConfig()).anomalies
    assert len(evaluate_rec_07(insufficient, REFERENCE_AT, ReconciliationConfig()).anomalies) == 1
    evaluation = evaluate_rec_07(unknown_expected, REFERENCE_AT, ReconciliationConfig())
    assert not evaluation.anomalies
    assert len(evaluation.not_evaluated) == 1
    assert "cannot be verified" in evaluation.not_evaluated[0].reason


def test_rec07_ambiguous_unlinked_refund_is_not_evaluated() -> None:
    context, _ = _context(
        returns=(_return("RETURN-1"), _return("RETURN-2")),
        refunds=(_refund(return_id=""),),
    )
    evaluation = evaluate_rec_07(context, REFERENCE_AT, ReconciliationConfig())
    assert not evaluation.anomalies
    assert len(evaluation.not_evaluated) == 2
    assert all("unambiguously" in item.reason for item in evaluation.not_evaluated)


def test_rec07_unlinked_refund_is_ambiguous_across_all_order_returns() -> None:
    context, frames = _context(
        returns=(
            _return("RETURN-RECEIVED", expected="100.00"),
            _return("RETURN-REQUESTED", status="requested"),
        ),
        refunds=(_refund(amount="100.00", return_id=""),),
    )
    originals = {name: frame.copy(deep=True) for name, frame in frames.items()}

    evaluation = evaluate_rec_07(context, REFERENCE_AT, ReconciliationConfig())

    assert not evaluation.anomalies
    assert len(evaluation.not_evaluated) == 1
    unavailable = evaluation.not_evaluated[0]
    assert "unambiguously" in unavailable.reason
    assert "multiple returns" in unavailable.reason
    assert {reference.record_id for reference in unavailable.record_references} == {
        "shopify:ORDER-1",
        "RETURN-RECEIVED",
        "RETURN-REQUESTED",
        "REFUND-1|PROVIDER-REFUND-1",
    }
    for filename, frame in frames.items():
        pd.testing.assert_frame_equal(frame, originals[filename])


def test_rec08_positive_boundary_ignored_and_aggregate_refunds() -> None:
    excessive, _ = _context(payments=(_payment(),), refunds=(_refund(amount="100.02"),))
    boundary, _ = _context(payments=(_payment(),), refunds=(_refund(amount="100.01"),))
    ignored, _ = _context(payments=(_payment(),), refunds=(_refund(amount="999.00", status="failed"),))
    aggregate, _ = _context(
        payments=(_payment(),),
        refunds=(_refund("REFUND-1", "60.00"), _refund("REFUND-2", "50.00")),
    )
    assert len(evaluate_rec_08(excessive, REFERENCE_AT, ReconciliationConfig()).anomalies) == 1
    assert not evaluate_rec_08(boundary, REFERENCE_AT, ReconciliationConfig()).anomalies
    assert not evaluate_rec_08(ignored, REFERENCE_AT, ReconciliationConfig()).anomalies
    assert len(evaluate_rec_08(aggregate, REFERENCE_AT, ReconciliationConfig()).anomalies) == 1


def test_rec09_overlapping_keys_unique_and_missing_provider() -> None:
    duplicate, _ = _context(
        refunds=(
            _refund("REFUND-1", provider_id="PROVIDER-1"),
            _refund("REFUND-1", provider_id="PROVIDER-1"),
            _refund("REFUND-2", provider_id="PROVIDER-1"),
        )
    )
    unique, _ = _context(refunds=(_refund("REFUND-1"), _refund("REFUND-2")))
    missing_provider, _ = _context(
        refunds=(
            _refund("REFUND-1", provider_id=""),
            _refund("REFUND-1", provider_id=""),
        )
    )
    anomalies = evaluate_rec_09(duplicate, REFERENCE_AT, ReconciliationConfig()).anomalies
    assert len(anomalies) == 1
    assert anomalies[0].compared_values["duplicate_record_count"] == "3"
    assert not evaluate_rec_09(unique, REFERENCE_AT, ReconciliationConfig()).anomalies
    assert len(evaluate_rec_09(missing_provider, REFERENCE_AT, ReconciliationConfig()).anomalies) == 1


def test_rec10_order_declared_events_positive_and_negative() -> None:
    missing, _ = _context(
        orders=(_order(payment_status="refunded", fulfillment_status="returned"),)
    )
    complete, _ = _context(
        payments=(_payment(),),
        shipments=(_shipment(),),
        returns=(_return(),),
        refunds=(_refund(),),
    )
    anomalies = evaluate_rec_10(missing, (), REFERENCE_AT, ReconciliationConfig()).anomalies
    assert len(anomalies) == 3
    assert {item.severity for item in anomalies} == {Severity.CRITICAL, Severity.HIGH}
    assert not evaluate_rec_10(complete, (), REFERENCE_AT, ReconciliationConfig()).anomalies


@pytest.mark.parametrize("code", ["REC-06", "REC-07", "REC-08", "REC-09", "REC-10"])
def test_rec06_to_rec10_permanent_scenarios_are_isolated_and_deterministic(code: str) -> None:
    manifest = json.loads((SAMPLE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    scenario = next(item for item in manifest["scenarios"] if item["code"] == code)
    validation = validate_dataset_directory(SAMPLE_ROOT / scenario["directory"])
    assert validation.dataframes is not None
    context = ReconciliationContext.from_dataframes(validation.dataframes)
    reference_at = datetime.fromisoformat(scenario["reference_at"]) if scenario["reference_at"] else REFERENCE_AT
    functions = {
        "REC-06": lambda: evaluate_rec_06(context, reference_at, ReconciliationConfig()),
        "REC-07": lambda: evaluate_rec_07(context, reference_at, ReconciliationConfig()),
        "REC-08": lambda: evaluate_rec_08(context, reference_at, ReconciliationConfig()),
        "REC-09": lambda: evaluate_rec_09(context, reference_at, ReconciliationConfig()),
        "REC-10": lambda: evaluate_rec_10(
            context,
            tuple(validation.report.messages),
            reference_at,
            ReconciliationConfig(),
        ),
    }
    first = functions[code]()
    second = functions[code]()
    assert first == second
    assert len(first.anomalies) == 1
    anomaly = first.anomalies[0]
    assert anomaly.anomaly_code.value == scenario["anomaly_code"]
    assert anomaly.order_id == scenario["affected_order_ids"][0]
    assert anomaly.description and anomaly.recommended_action


def test_rec06_to_rec10_do_not_modify_input_frames() -> None:
    context, frames = _context(
        orders=(_order(order_status="cancelled", payment_status="refunded", fulfillment_status="returned"),),
        payments=(_payment(),),
        shipments=(_shipment(),),
        returns=(_return(),),
        refunds=(_refund(),),
    )
    originals = {name: frame.copy(deep=True) for name, frame in frames.items()}
    evaluate_rec_06(context, REFERENCE_AT, ReconciliationConfig())
    evaluate_rec_07(context, REFERENCE_AT, ReconciliationConfig())
    evaluate_rec_08(context, REFERENCE_AT, ReconciliationConfig())
    evaluate_rec_09(context, REFERENCE_AT, ReconciliationConfig())
    evaluate_rec_10(context, (), REFERENCE_AT, ReconciliationConfig())
    for filename, frame in frames.items():
        pd.testing.assert_frame_equal(frame, originals[filename])
