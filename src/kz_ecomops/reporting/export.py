"""Pure, deterministic CSV reporting for reconciliation anomalies."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta, timezone
from decimal import Decimal, localcontext
from types import MappingProxyType

from kz_ecomops.reconciliation import (
    ReconciliationAnomaly,
    ReconciliationResult,
)


ANOMALY_EXPORT_COLUMNS = (
    "anomaly_id",
    "rule_code",
    "anomaly_code",
    "order_id",
    "platform",
    "problem_type",
    "description",
    "severity",
    "detected_at",
    "recommended_action",
    "review_status",
    "compared_values_json",
    "record_references_json",
    "reference_at",
    "monetary_tolerance",
    "currency",
    "shipping_limit_hours",
    "return_refund_limit_days",
    "high_shipping_delay_threshold_hours",
)

_FORMULA_PREFIXES = ("=", "+", "-", "@")


@dataclass(frozen=True, slots=True)
class AnomalyCsvExport:
    """Contain a complete in-memory anomaly export ready for download."""

    filename: str
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, str], ...]
    content: bytes

    @property
    def row_count(self) -> int:
        """Return the number of exported anomalies, excluding the header."""

        return len(self.rows)


def neutralize_spreadsheet_formula(value: str) -> str:
    """Prefix risky text with an apostrophe so spreadsheets treat it as text.

    The original value, including leading spaces, remains present after the
    neutralizing apostrophe. JSON, dates, and numeric fields bypass this helper.
    """

    if not isinstance(value, str):
        raise TypeError("Spreadsheet text values must be strings.")
    stripped = value.lstrip()
    if stripped.startswith(_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def _json_text(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _duration_text(value: timedelta, unit: timedelta) -> str:
    total_microseconds = (
        (value.days * 86_400 + value.seconds) * 1_000_000
        + value.microseconds
    )
    unit_microseconds = (
        (unit.days * 86_400 + unit.seconds) * 1_000_000
        + unit.microseconds
    )
    quotient, remainder = divmod(total_microseconds, unit_microseconds)
    if remainder == 0:
        return str(quotient)
    with localcontext() as context:
        context.prec = max(50, len(str(abs(total_microseconds))) + 30)
        decimal_value = Decimal(total_microseconds) / Decimal(unit_microseconds)
    text = format(decimal_value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def anomaly_export_filename(result: ReconciliationResult) -> str:
    """Build a deterministic UTC filename from the result reference time."""

    reference_at = result.reference_at.astimezone(timezone.utc)
    return f"kz-ecomops-anomalies-{reference_at:%Y%m%d-%H%M%SZ}.csv"


def build_anomaly_export_rows(
    result: ReconciliationResult,
    anomalies: Iterable[ReconciliationAnomaly] | None = None,
) -> tuple[Mapping[str, str], ...]:
    """Build immutable, deterministically ordered rows without mutating inputs."""

    selected = tuple(result.anomalies if anomalies is None else anomalies)
    if any(not isinstance(item, ReconciliationAnomaly) for item in selected):
        raise TypeError("anomalies must contain ReconciliationAnomaly objects.")
    ordered = sorted(
        selected,
        key=lambda item: (
            item.anomaly_id,
            item.rule_code.value,
            item.platform,
            item.order_id or "",
        ),
    )
    config = result.config
    reference_at = result.reference_at.astimezone(timezone.utc).isoformat()
    high_threshold = config.high_shipping_delay_threshold
    rows: list[Mapping[str, str]] = []
    for anomaly in ordered:
        references = [
            {
                "filename": reference.filename,
                "row_number": reference.row_number,
                "record_id": reference.record_id,
            }
            for reference in sorted(anomaly.record_references)
        ]
        row = {
            "anomaly_id": neutralize_spreadsheet_formula(anomaly.anomaly_id),
            "rule_code": neutralize_spreadsheet_formula(anomaly.rule_code.value),
            "anomaly_code": neutralize_spreadsheet_formula(
                anomaly.anomaly_code.value
            ),
            "order_id": neutralize_spreadsheet_formula(anomaly.order_id or ""),
            "platform": neutralize_spreadsheet_formula(anomaly.platform),
            "problem_type": neutralize_spreadsheet_formula(
                anomaly.problem_type.value
            ),
            "description": neutralize_spreadsheet_formula(anomaly.description),
            "severity": neutralize_spreadsheet_formula(anomaly.severity.value),
            "detected_at": anomaly.detected_at.isoformat(),
            "recommended_action": neutralize_spreadsheet_formula(
                anomaly.recommended_action
            ),
            "review_status": neutralize_spreadsheet_formula(
                anomaly.review_status.value
            ),
            "compared_values_json": _json_text(dict(anomaly.compared_values)),
            "record_references_json": _json_text(references),
            "reference_at": reference_at,
            "monetary_tolerance": str(config.monetary_tolerance),
            "currency": "EUR",
            "shipping_limit_hours": _duration_text(
                config.shipping_limit,
                timedelta(hours=1),
            ),
            "return_refund_limit_days": _duration_text(
                config.return_refund_limit,
                timedelta(days=1),
            ),
            "high_shipping_delay_threshold_hours": (
                _duration_text(high_threshold, timedelta(hours=1))
                if high_threshold is not None
                else ""
            ),
        }
        rows.append(MappingProxyType(row))
    return tuple(rows)


def generate_anomaly_csv(rows: Sequence[Mapping[str, str]]) -> bytes:
    """Render rows as deterministic RFC-style CSV bytes with a UTF-8 BOM."""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=ANOMALY_EXPORT_COLUMNS,
        extrasaction="raise",
        lineterminator="\r\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row))
    return output.getvalue().encode("utf-8-sig")


def build_anomaly_export(
    result: ReconciliationResult,
    anomalies: Iterable[ReconciliationAnomaly] | None = None,
) -> AnomalyCsvExport:
    """Build a complete deterministic anomaly CSV entirely in memory."""

    rows = build_anomaly_export_rows(result, anomalies)
    content = generate_anomaly_csv(rows)
    return AnomalyCsvExport(
        filename=anomaly_export_filename(result),
        columns=ANOMALY_EXPORT_COLUMNS,
        rows=rows,
        content=content,
    )


__all__ = [
    "ANOMALY_EXPORT_COLUMNS",
    "AnomalyCsvExport",
    "anomaly_export_filename",
    "build_anomaly_export",
    "build_anomaly_export_rows",
    "generate_anomaly_csv",
    "neutralize_spreadsheet_formula",
]
