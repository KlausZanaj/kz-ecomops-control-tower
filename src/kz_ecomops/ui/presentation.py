"""Pure presentation models for Streamlit metrics, filters, and details."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from decimal import Decimal
from types import MappingProxyType

from kz_ecomops.reconciliation import (
    ReconciliationAnomaly,
    ReconciliationResult,
    RuleNotEvaluated,
)
from kz_ecomops.validation import DatasetValidationResult


NOT_CALCULATED = "Not calculated"
_SEVERITY_LABELS = {
    "critical": "⛔ Critical",
    "high": "⚠ High",
    "medium": "● Medium",
    "low": "○ Low",
}


def operational_summary(
    validation: DatasetValidationResult | None,
    reconciliation: ReconciliationResult | None,
) -> Mapping[str, str]:
    """Return truthful KPI text without treating unavailable values as zero."""

    values = {
        "Orders": NOT_CALCULATED,
        "Order total": NOT_CALCULATED,
        "Valid payments": NOT_CALCULATED,
        "Shipments": NOT_CALCULATED,
        "Returns": NOT_CALCULATED,
        "Refunds": NOT_CALCULATED,
        "Reconciliation status": NOT_CALCULATED,
        "Anomalies": NOT_CALCULATED,
        "Checks not evaluated": NOT_CALCULATED,
    }
    if validation is not None and validation.dataframes is not None:
        frames = validation.dataframes
        order_total = sum(
            (Decimal(value) for value in frames["orders.csv"]["order_total"]),
            Decimal("0"),
        )
        values.update(
            {
                "Orders": str(len(frames["orders.csv"])),
                "Order total": f"{order_total:.2f} EUR",
                "Valid payments": str(len(frames["payments.csv"])),
                "Shipments": str(len(frames["shipments.csv"])),
                "Returns": str(len(frames["returns.csv"])),
                "Refunds": str(len(frames["refunds.csv"])),
                "Reconciliation status": "Ready, not run",
            }
        )
    elif validation is not None:
        values["Reconciliation status"] = "Unavailable — validation is blocking"
    if reconciliation is not None:
        values.update(
            {
                "Reconciliation status": "Completed",
                "Anomalies": str(len(reconciliation.anomalies)),
                "Checks not evaluated": str(len(reconciliation.not_evaluated)),
            }
        )
    return MappingProxyType(values)


def filter_anomalies(
    anomalies: Sequence[ReconciliationAnomaly],
    *,
    platforms: Collection[str] = (),
    anomaly_codes: Collection[str] = (),
    severities: Collection[str] = (),
    review_statuses: Collection[str] = (),
) -> tuple[ReconciliationAnomaly, ...]:
    """Apply all selected filters with AND semantics and no mutations."""

    return tuple(
        anomaly
        for anomaly in anomalies
        if (not platforms or anomaly.platform in platforms)
        and (not anomaly_codes or anomaly.anomaly_code.value in anomaly_codes)
        and (not severities or anomaly.severity.value in severities)
        and (not review_statuses or anomaly.review_status.value in review_statuses)
    )


def anomaly_table_rows(
    anomalies: Sequence[ReconciliationAnomaly],
) -> tuple[Mapping[str, str], ...]:
    """Build the readable anomaly table required by the MVP."""

    return tuple(
        MappingProxyType(
            {
                "Anomaly ID": anomaly.anomaly_id,
                "Rule": anomaly.rule_code.value,
                "Anomaly code": anomaly.anomaly_code.value,
                "Order ID": anomaly.order_id or "Not available",
                "Platform": anomaly.platform,
                "Problem type": anomaly.problem_type.value,
                "Severity": _SEVERITY_LABELS[anomaly.severity.value],
                "Review status": anomaly.review_status.value,
                "Detected at": anomaly.detected_at.isoformat(),
                "Description": anomaly.description,
            }
        )
        for anomaly in anomalies
    )


def anomaly_detail(anomaly: ReconciliationAnomaly) -> Mapping[str, object]:
    """Expose every RF-19 field, applied rule, compared values, and references."""

    references = tuple(
        MappingProxyType(
            {
                "Filename": reference.filename,
                "Row number": str(reference.row_number),
                "Record ID": reference.record_id,
            }
        )
        for reference in anomaly.record_references
    )
    return MappingProxyType(
        {
            "Anomaly ID": anomaly.anomaly_id,
            "Rule code": anomaly.rule_code.value,
            "Anomaly code": anomaly.anomaly_code.value,
            "Order ID": anomaly.order_id or "Not available",
            "Platform": anomaly.platform,
            "Problem type": anomaly.problem_type.value,
            "Description": anomaly.description,
            "Severity": _SEVERITY_LABELS[anomaly.severity.value],
            "Detected at": anomaly.detected_at.isoformat(),
            "Recommended action": anomaly.recommended_action,
            "Review status": anomaly.review_status.value,
            "Compared values": MappingProxyType(dict(anomaly.compared_values)),
            "Record references": references,
        }
    )


def not_evaluated_rows(
    items: Sequence[RuleNotEvaluated],
) -> tuple[Mapping[str, str], ...]:
    """Present unavailable rule checks separately from confirmed anomalies."""

    return tuple(
        MappingProxyType(
            {
                "Rule": item.rule_code.value,
                "Order ID": item.order_id or "Not available",
                "Platform": item.platform,
                "Reason": item.reason,
                "References": "; ".join(
                    f"{reference.filename} row {reference.row_number} "
                    f"({reference.record_id})"
                    for reference in item.record_references
                )
                or "None",
            }
        )
        for item in items
    )
