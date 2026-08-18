"""Pure integration between current UI filters and anomaly reporting."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from kz_ecomops.reconciliation import ReconciliationAnomaly, ReconciliationResult
from kz_ecomops.reporting import AnomalyCsvExport, build_anomaly_export

from .presentation import filter_anomalies


@dataclass(frozen=True, slots=True)
class FilteredAnomalyReport:
    """Bind one exact filtered anomaly selection to its in-memory export."""

    anomalies: tuple[ReconciliationAnomaly, ...]
    export: AnomalyCsvExport


def build_filtered_anomaly_report(
    result: ReconciliationResult,
    *,
    platforms: Collection[str] = (),
    anomaly_codes: Collection[str] = (),
    severities: Collection[str] = (),
    review_statuses: Collection[str] = (),
) -> FilteredAnomalyReport:
    """Apply all current filters and export exactly the matching anomalies."""

    selected = filter_anomalies(
        result.anomalies,
        platforms=platforms,
        anomaly_codes=anomaly_codes,
        severities=severities,
        review_statuses=review_statuses,
    )
    return FilteredAnomalyReport(
        anomalies=selected,
        export=build_anomaly_export(result, selected),
    )


__all__ = ["FilteredAnomalyReport", "build_filtered_anomaly_report"]
