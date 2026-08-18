"""Pure, deterministic anomaly distributions for operational reporting."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from kz_ecomops.reconciliation import ReconciliationAnomaly


@dataclass(frozen=True, slots=True)
class AnomalyDistributions:
    """Contain stable counts for one explicit anomaly selection."""

    total_count: int
    by_anomaly_code: Mapping[str, int]
    by_severity: Mapping[str, int]
    by_platform: Mapping[str, int]
    by_review_status: Mapping[str, int]


def _stable_counts(values: Iterable[str]) -> Mapping[str, int]:
    counts = Counter(values)
    return MappingProxyType(dict(sorted(counts.items())))


def anomaly_distributions(
    anomalies: Iterable[ReconciliationAnomaly],
) -> AnomalyDistributions:
    """Count four operational dimensions without mutating or sorting the input."""

    selected = tuple(anomalies)
    if any(not isinstance(item, ReconciliationAnomaly) for item in selected):
        raise TypeError("anomalies must contain ReconciliationAnomaly objects.")
    return AnomalyDistributions(
        total_count=len(selected),
        by_anomaly_code=_stable_counts(
            item.anomaly_code.value for item in selected
        ),
        by_severity=_stable_counts(item.severity.value for item in selected),
        by_platform=_stable_counts(item.platform for item in selected),
        by_review_status=_stable_counts(
            item.review_status.value for item in selected
        ),
    )


__all__ = ["AnomalyDistributions", "anomaly_distributions"]
