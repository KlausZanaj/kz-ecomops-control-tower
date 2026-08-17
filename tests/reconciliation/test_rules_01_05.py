"""Rule-level tests for deterministic REC-01 through REC-05 checks."""

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
    evaluate_rec_01,
    evaluate_rec_02,
    evaluate_rec_03,
    evaluate_rec_04,
    evaluate_rec_05,
)
from kz_ecomops.reconciliation.context import ReconciliationContext
from kz_ecomops.validation import CSV_SCHEMAS, validate_dataset_directory


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = PROJECT_ROOT / "data" / "sample"
REFERENCE_AT = datetime(2026, 3, 4, 12, tzinfo=timezone.utc)
RULES = {
    RuleCode.REC_01: evaluate_rec_01,
    RuleCode.REC_02: evaluate_rec_02,
    RuleCode.REC_03: evaluate_rec_03,
    RuleCode.REC_04: evaluate_rec_04,
    RuleCode.REC_05: evaluate_rec_05,
}


def _row(filename: str, **values: str) -> dict[str, str]:
    row = {column: "" for column in CSV_SCHEMAS[filename].column_names}
    row.update(values)
    return row


def _context(
    *,
    order_status: str = "confirmed",
    payment_status: str = "paid",
    order_total: str = "100.00",
    payments: tuple[dict[str, str], ...] = (),
    shipments: tuple[dict[str, str], ...] = (),
    returns: tuple[dict[str, str], ...] = (),
    refunds: tuple[dict[str, str], ...] = (),
) -> tuple[ReconciliationContext, dict[str, pd.DataFrame]]:
    order_id = "shopify:ORDER-1"
    orders = (
        _row(
            "orders.csv",
            order_id=order_id,
            platform="shopify",
            source_order_id="ORDER-1",
            order_status=order_status,
            payment_status=payment_status,
            fulfillment_status="unfulfilled",
            currency="EUR",
            order_total=order_total,
        ),
    )
    frames = {
        "orders.csv": pd.DataFrame(orders, columns=CSV_SCHEMAS["orders.csv"].column_names, dtype=str),
        "payments.csv": pd.DataFrame(payments, columns=CSV_SCHEMAS["payments.csv"].column_names, dtype=str),
        "shipments.csv": pd.DataFrame(shipments, columns=CSV_SCHEMAS["shipments.csv"].column_names, dtype=str),
        "returns.csv": pd.DataFrame(returns, columns=CSV_SCHEMAS["returns.csv"].column_names, dtype=str),
        "refunds.csv": pd.DataFrame(refunds, columns=CSV_SCHEMAS["refunds.csv"].column_names, dtype=str),
    }
    return ReconciliationContext.from_dataframes(frames), frames


def _payment(
    payment_id: str,
    amount: str,
    *,
    status: str = "succeeded",
    provider_id: str = "",
    paid_at: str = "2026-03-01T10:00:00+00:00",
) -> dict[str, str]:
    return _row(
        "payments.csv",
        payment_id=payment_id,
        platform="shopify",
        order_id="shopify:ORDER-1",
        source_order_id="ORDER-1",
        provider_transaction_id=provider_id,
        payment_status=status,
        amount=amount,
        currency="EUR",
        paid_at=paid_at if status == "succeeded" else "",
    )


def _shipment(
    shipment_id: str = "SHIP-1",
    *,
    status: str = "shipped",
    tracking: str = "TRACK-1",
) -> dict[str, str]:
    return _row(
        "shipments.csv",
        shipment_id=shipment_id,
        platform="shopify",
        order_id="shopify:ORDER-1",
        source_order_id="ORDER-1",
        shipment_status=status,
        tracking_number=tracking,
        shipped_at="2026-03-02T10:00:00+00:00" if status in {"shipped", "delivered"} else "",
        delivered_at="2026-03-03T10:00:00+00:00" if status == "delivered" else "",
    )


def _run(rule: RuleCode, context: ReconciliationContext, *, reference_at: datetime = REFERENCE_AT, config: ReconciliationConfig | None = None):
    return RULES[rule](context, reference_at, config or ReconciliationConfig())


def test_rec01_positive_negative_boundary_and_ignored_statuses() -> None:
    mismatch, _ = _context(payments=(_payment("PAY-1", "90.00"),))
    exact, _ = _context(payments=(_payment("PAY-1", "100.00"),))
    boundary, _ = _context(payments=(_payment("PAY-1", "99.99"),))
    ignored, _ = _context(payments=(_payment("PAY-1", "100.00", status="pending"),))

    assert len(_run(RuleCode.REC_01, mismatch).anomalies) == 1
    assert not _run(RuleCode.REC_01, exact).anomalies
    assert not _run(RuleCode.REC_01, boundary).anomalies
    assert not _run(RuleCode.REC_01, ignored).anomalies


def test_rec01_aggregates_succeeded_and_reversed_payments() -> None:
    context, _ = _context(
        payments=(
            _payment("PAY-1", "60.00"),
            _payment("PAY-2", "50.00"),
            _payment("PAY-3", "10.00", status="reversed"),
            _payment("PAY-4", "999.00", status="failed"),
        )
    )
    assert not _run(RuleCode.REC_01, context).anomalies


def test_rec02_boundary_cancelled_high_threshold_and_completion_time() -> None:
    context, _ = _context(
        payments=(
            _payment("PAY-1", "60.00", paid_at="2026-03-01T09:00:00+00:00"),
            _payment("PAY-2", "40.00", paid_at="2026-03-01T10:00:00+00:00"),
        )
    )
    exact = datetime(2026, 3, 3, 10, tzinfo=timezone.utc)
    assert not _run(RuleCode.REC_02, context, reference_at=exact).anomalies
    medium = _run(RuleCode.REC_02, context, reference_at=exact + timedelta(seconds=1)).anomalies
    assert len(medium) == 1 and medium[0].severity is Severity.MEDIUM
    high = _run(
        RuleCode.REC_02,
        context,
        reference_at=datetime(2026, 3, 5, 10, 0, 1, tzinfo=timezone.utc),
        config=ReconciliationConfig(high_shipping_delay_threshold=timedelta(hours=72)),
    ).anomalies
    assert high[0].severity is Severity.HIGH
    cancelled, _ = _context(order_status="cancelled", payments=(_payment("PAY-1", "100.00"),))
    assert not _run(RuleCode.REC_02, cancelled).anomalies


def test_rec02_ignores_unconfirmed_payment_and_departed_shipment() -> None:
    pending, _ = _context(payments=(_payment("PAY-1", "100.00", status="pending"),))
    shipped, _ = _context(
        payments=(_payment("PAY-1", "100.00"),),
        shipments=(_shipment(),),
    )
    assert not _run(RuleCode.REC_02, pending).anomalies
    assert not _run(RuleCode.REC_02, shipped).anomalies


def test_rec03_positive_full_payment_boundary_ignored_and_aggregate() -> None:
    insufficient, _ = _context(payments=(_payment("PAY-1", "90.00"),), shipments=(_shipment(),))
    complete, _ = _context(payments=(_payment("PAY-1", "100.00"),), shipments=(_shipment(),))
    boundary, _ = _context(payments=(_payment("PAY-1", "99.99"),), shipments=(_shipment(),))
    pending, _ = _context(payments=(_payment("PAY-1", "100.00", status="pending"),), shipments=(_shipment(),))
    aggregate, _ = _context(
        payments=(_payment("PAY-1", "50.00"), _payment("PAY-2", "40.00")),
        shipments=(_shipment(),),
    )
    assert len(_run(RuleCode.REC_03, insufficient).anomalies) == 1
    assert not _run(RuleCode.REC_03, complete).anomalies
    assert not _run(RuleCode.REC_03, boundary).anomalies
    assert len(_run(RuleCode.REC_03, pending).anomalies) == 1
    assert len(_run(RuleCode.REC_03, aggregate).anomalies) == 1


def test_rec04_groups_overlapping_duplicate_keys_once_and_preserves_references() -> None:
    context, _ = _context(
        payments=(
            _payment("PAY-1", "50.00", provider_id="TXN-1"),
            _payment("PAY-1", "50.00", provider_id="TXN-1"),
            _payment("PAY-2", "50.00", provider_id="TXN-1"),
        )
    )
    anomalies = _run(RuleCode.REC_04, context).anomalies
    assert len(anomalies) == 1
    assert anomalies[0].compared_values["duplicate_record_count"] == "3"
    assert len(anomalies[0].record_references) == 4


def test_rec04_single_unique_and_missing_provider_behavior() -> None:
    unique, _ = _context(
        payments=(
            _payment("PAY-1", "50.00"),
            _payment("PAY-2", "50.00"),
        )
    )
    duplicate_id, _ = _context(
        payments=(
            _payment("PAY-1", "50.00"),
            _payment("PAY-1", "50.00"),
        )
    )
    assert not _run(RuleCode.REC_04, unique).anomalies
    assert len(_run(RuleCode.REC_04, duplicate_id).anomalies) == 1


def test_rec05_one_per_shipment_whitespace_boundary_and_ignored_status() -> None:
    context, _ = _context(
        shipments=(
            _shipment("SHIP-1", tracking=""),
            _shipment("SHIP-2", status="delivered", tracking="   "),
            _shipment("SHIP-3", status="pending", tracking=""),
            _shipment("SHIP-4", tracking="TRACK-4"),
        )
    )
    anomalies = _run(RuleCode.REC_05, context).anomalies
    assert len(anomalies) == 2
    assert {item.compared_values["shipment_id"] for item in anomalies} == {"SHIP-1", "SHIP-2"}


@pytest.mark.parametrize("rule_code", list(RULES))
def test_rec01_to_rec05_scenarios_are_isolated_and_deterministic(rule_code: RuleCode) -> None:
    manifest = json.loads((SAMPLE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    scenario = next(item for item in manifest["scenarios"] if item["code"] == rule_code.value)
    validation = validate_dataset_directory(SAMPLE_ROOT / scenario["directory"])
    assert validation.dataframes is not None
    context = ReconciliationContext.from_dataframes(validation.dataframes)
    reference_at = datetime.fromisoformat(scenario["reference_at"]) if scenario["reference_at"] else REFERENCE_AT

    first = _run(rule_code, context, reference_at=reference_at)
    second = _run(rule_code, context, reference_at=reference_at)

    assert first == second
    assert len(first.anomalies) == 1
    anomaly = first.anomalies[0]
    assert anomaly.anomaly_code.value == scenario["anomaly_code"]
    assert anomaly.order_id == scenario["affected_order_ids"][0]
    assert anomaly.description and anomaly.recommended_action


def test_rec01_to_rec05_do_not_modify_input_frames() -> None:
    context, frames = _context(
        payments=(
            _payment("PAY-1", "90.00", provider_id="TXN-1"),
            _payment("PAY-1", "90.00", provider_id="TXN-1"),
        ),
        shipments=(_shipment(tracking=""),),
    )
    originals = {name: frame.copy(deep=True) for name, frame in frames.items()}

    for rule_code in RULES:
        _run(rule_code, context)

    for filename, frame in frames.items():
        pd.testing.assert_frame_equal(frame, originals[filename])
