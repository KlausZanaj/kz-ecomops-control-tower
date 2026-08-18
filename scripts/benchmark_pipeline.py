"""Deterministic benchmark for the complete CSV validation and reconciliation pipeline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from kz_ecomops.reconciliation import reconcile_dataset
from kz_ecomops.validation import CSV_SCHEMAS, validate_dataset_directory


BENCHMARK_FILENAMES = tuple(CSV_SCHEMAS)
DEFAULT_TOTAL_ROWS = 100_000
DEFAULT_RUNS = 3
DEFAULT_TARGET_SECONDS = 30.0
REFERENCE_AT = datetime(2026, 3, 20, 12, tzinfo=timezone.utc)
PLATFORMS = ("shopify", "woocommerce", "amazon", "ebay")


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    """Measured timings and deterministic result counts for one pipeline run."""

    validation_seconds: float
    reconciliation_seconds: float
    total_seconds: float
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    anomaly_count: int
    not_evaluated_count: int
    reconciliation_ready: bool

    @property
    def result_fingerprint(self) -> tuple[int, int, int, int, int, bool]:
        return (
            self.total_rows,
            self.accepted_rows,
            self.rejected_rows,
            self.anomaly_count,
            self.not_evaluated_count,
            self.reconciliation_ready,
        )


@dataclass(frozen=True, slots=True)
class TimingStatistics:
    """Minimum, median, and maximum values for one timing dimension."""

    minimum: float
    median: float
    maximum: float


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    """Complete reproducible benchmark report without retaining generated data."""

    total_rows: int
    rows_by_file: Mapping[str, int]
    generation_seconds: float
    warm_up_fingerprint: tuple[int, int, int, int, int, bool]
    measured_runs: tuple[BenchmarkRun, ...]
    validation: TimingStatistics
    reconciliation: TimingStatistics
    total: TimingStatistics
    target_seconds: float
    results_consistent: bool
    target_met: bool

    def as_json_data(self) -> dict[str, object]:
        """Return a stable-key JSON-ready representation."""

        return {
            "generation_seconds": self.generation_seconds,
            "measured_runs": [asdict(run) for run in self.measured_runs],
            "results_consistent": self.results_consistent,
            "rows_by_file": dict(sorted(self.rows_by_file.items())),
            "schema_version": 1,
            "target_met": self.target_met,
            "target_seconds": self.target_seconds,
            "timing_statistics": {
                "reconciliation": asdict(self.reconciliation),
                "total": asdict(self.total),
                "validation": asdict(self.validation),
            },
            "total_rows": self.total_rows,
            "warm_up_excluded": True,
            "warm_up_fingerprint": list(self.warm_up_fingerprint),
        }


def rows_per_file(total_rows: int) -> int:
    """Return the equal five-file distribution required by the benchmark."""

    if isinstance(total_rows, bool) or not isinstance(total_rows, int):
        raise TypeError("total_rows must be an integer.")
    if total_rows < len(BENCHMARK_FILENAMES):
        raise ValueError("total_rows must provide at least one row per CSV file.")
    if total_rows % len(BENCHMARK_FILENAMES):
        raise ValueError("total_rows must be divisible by five.")
    return total_rows // len(BENCHMARK_FILENAMES)


def _record_context(index: int) -> dict[str, str]:
    platform = PLATFORMS[index % len(PLATFORMS)]
    source_order_id = f"BENCH-{index + 1:08d}"
    order_id = f"{platform}:{source_order_id}"
    amount = f"{100 + index % 100}.00"
    return {
        "amount": amount,
        "order_id": order_id,
        "payment_id": f"pay-{source_order_id}",
        "platform": platform,
        "return_id": f"ret-{source_order_id}",
        "source_order_id": source_order_id,
    }


def _row(filename: str, index: int) -> dict[str, str]:
    item = _record_context(index)
    if filename == "orders.csv":
        return {
            "order_id": item["order_id"],
            "platform": item["platform"],
            "source_order_id": item["source_order_id"],
            "order_number": f"DEMO-{item['source_order_id']}",
            "ordered_at": "2026-01-01T10:00:00+00:00",
            "order_status": "completed",
            "payment_status": "refunded",
            "fulfillment_status": "returned",
            "currency": "EUR",
            "subtotal": item["amount"],
            "discount_total": "0.00",
            "shipping_total": "0.00",
            "tax_total": "0.00",
            "order_total": item["amount"],
            "customer_country": "IT",
            "cancelled_at": "",
            "cancellation_reason": "",
            "updated_at": "2026-01-06T10:00:00+00:00",
        }
    if filename == "payments.csv":
        return {
            "payment_id": item["payment_id"],
            "platform": item["platform"],
            "order_id": item["order_id"],
            "source_order_id": item["source_order_id"],
            "provider_transaction_id": f"txn-{item['source_order_id']}",
            "payment_method": "synthetic_card",
            "payment_status": "succeeded",
            "amount": item["amount"],
            "currency": "EUR",
            "paid_at": "2026-01-01T10:05:00+00:00",
            "created_at": "2026-01-01T10:04:00+00:00",
            "updated_at": "2026-01-01T10:05:00+00:00",
        }
    if filename == "shipments.csv":
        return {
            "shipment_id": f"ship-{item['source_order_id']}",
            "platform": item["platform"],
            "order_id": item["order_id"],
            "source_order_id": item["source_order_id"],
            "shipment_status": "delivered",
            "carrier": "synthetic_carrier",
            "shipping_service": "standard",
            "tracking_number": f"track-{item['source_order_id']}",
            "shipped_at": "2026-01-02T10:00:00+00:00",
            "delivered_at": "2026-01-03T10:00:00+00:00",
            "warehouse_id": "synthetic-warehouse-01",
            "updated_at": "2026-01-03T10:00:00+00:00",
        }
    if filename == "returns.csv":
        return {
            "return_id": item["return_id"],
            "platform": item["platform"],
            "order_id": item["order_id"],
            "source_order_id": item["source_order_id"],
            "return_status": "completed",
            "return_reason": "synthetic_return",
            "requested_at": "2026-01-04T10:00:00+00:00",
            "received_at": "2026-01-05T10:00:00+00:00",
            "expected_refund_amount": item["amount"],
            "currency": "EUR",
            "updated_at": "2026-01-05T10:00:00+00:00",
        }
    if filename == "refunds.csv":
        return {
            "refund_id": f"ref-{item['source_order_id']}",
            "platform": item["platform"],
            "order_id": item["order_id"],
            "source_order_id": item["source_order_id"],
            "return_id": item["return_id"],
            "payment_id": item["payment_id"],
            "provider_refund_id": f"provider-ref-{item['source_order_id']}",
            "refund_status": "succeeded",
            "amount": item["amount"],
            "currency": "EUR",
            "reason": "synthetic_refund",
            "refunded_at": "2026-01-06T10:00:00+00:00",
            "created_at": "2026-01-06T09:59:00+00:00",
            "updated_at": "2026-01-06T10:00:00+00:00",
        }
    raise KeyError(f"Unsupported benchmark filename: {filename}")


def write_benchmark_dataset(directory: Path, total_rows: int) -> Mapping[str, int]:
    """Write one deterministic canonical benchmark dataset to an explicit path."""

    count = rows_per_file(total_rows)
    directory.mkdir(parents=True, exist_ok=False)
    counts: dict[str, int] = {}
    for filename, schema in CSV_SCHEMAS.items():
        path = directory / filename
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=schema.column_names,
                lineterminator="\n",
            )
            writer.writeheader()
            for index in range(count):
                writer.writerow(_row(filename, index))
        counts[filename] = count
    return counts


def dataset_digests(directory: Path) -> Mapping[str, str]:
    """Return stable SHA-256 digests for determinism checks."""

    return {
        filename: hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        for filename in BENCHMARK_FILENAMES
    }


def measure_pipeline(
    directory: Path,
    *,
    timer: Callable[[], float] = perf_counter,
) -> BenchmarkRun:
    """Measure complete validation and reconciliation as separate phases."""

    total_started = timer()
    validation_started = timer()
    validation = validate_dataset_directory(directory)
    validation_finished = timer()
    if not validation.report.reconciliation_ready:
        raise RuntimeError("Generated benchmark dataset is not reconciliation-ready.")
    reconciliation_started = timer()
    result = reconcile_dataset(validation, REFERENCE_AT)
    reconciliation_finished = timer()
    total_finished = timer()
    return BenchmarkRun(
        validation_seconds=validation_finished - validation_started,
        reconciliation_seconds=reconciliation_finished - reconciliation_started,
        total_seconds=total_finished - total_started,
        total_rows=validation.report.total_row_count,
        accepted_rows=validation.report.accepted_row_count,
        rejected_rows=validation.report.rejected_row_count,
        anomaly_count=len(result.anomalies),
        not_evaluated_count=len(result.not_evaluated),
        reconciliation_ready=validation.report.reconciliation_ready,
    )


def _timing_statistics(values: Sequence[float]) -> TimingStatistics:
    if not values:
        raise ValueError("At least one timing value is required.")
    return TimingStatistics(
        minimum=min(values),
        median=statistics.median(values),
        maximum=max(values),
    )


def summarize_benchmark(
    *,
    total_rows: int,
    rows_by_file: Mapping[str, int],
    generation_seconds: float,
    warm_up: BenchmarkRun,
    measured_runs: Sequence[BenchmarkRun],
    target_seconds: float,
) -> BenchmarkSummary:
    """Calculate deterministic statistics and the strict performance verdict."""

    runs = tuple(measured_runs)
    if len(runs) < DEFAULT_RUNS:
        raise ValueError("At least three measured runs are required.")
    fingerprints = (warm_up.result_fingerprint, *(run.result_fingerprint for run in runs))
    results_consistent = len(set(fingerprints)) == 1
    total_stats = _timing_statistics([run.total_seconds for run in runs])
    return BenchmarkSummary(
        total_rows=total_rows,
        rows_by_file=dict(sorted(rows_by_file.items())),
        generation_seconds=generation_seconds,
        warm_up_fingerprint=warm_up.result_fingerprint,
        measured_runs=runs,
        validation=_timing_statistics([run.validation_seconds for run in runs]),
        reconciliation=_timing_statistics(
            [run.reconciliation_seconds for run in runs]
        ),
        total=total_stats,
        target_seconds=target_seconds,
        results_consistent=results_consistent,
        target_met=results_consistent and total_stats.maximum < target_seconds,
    )


def run_benchmark(
    *,
    total_rows: int = DEFAULT_TOTAL_ROWS,
    runs: int = DEFAULT_RUNS,
    target_seconds: float = DEFAULT_TARGET_SECONDS,
    temporary_parent: Path | None = None,
) -> BenchmarkSummary:
    """Generate, warm up, measure, and automatically remove one dataset."""

    rows_per_file(total_rows)
    if runs < DEFAULT_RUNS:
        raise ValueError("runs must be at least three.")
    if target_seconds <= 0:
        raise ValueError("target_seconds must be greater than zero.")
    parent = str(temporary_parent) if temporary_parent is not None else None
    with tempfile.TemporaryDirectory(
        prefix="kz-ecomops-benchmark-",
        dir=parent,
    ) as temporary:
        dataset = Path(temporary) / "dataset"
        generation_started = perf_counter()
        rows_by_file = write_benchmark_dataset(dataset, total_rows)
        generation_seconds = perf_counter() - generation_started
        warm_up = measure_pipeline(dataset)
        measured = tuple(measure_pipeline(dataset) for _ in range(runs))
        return summarize_benchmark(
            total_rows=total_rows,
            rows_by_file=rows_by_file,
            generation_seconds=generation_seconds,
            warm_up=warm_up,
            measured_runs=measured,
            target_seconds=target_seconds,
        )


def format_text_report(summary: BenchmarkSummary) -> str:
    """Build a concise human-readable benchmark report."""

    lines = [
        "KZ EcomOps deterministic pipeline benchmark",
        f"Rows: {summary.total_rows:,} total ({dict(summary.rows_by_file)})",
        f"Generation (excluded): {summary.generation_seconds:.6f} s",
        "Warm-up: completed and excluded",
    ]
    for index, run in enumerate(summary.measured_runs, start=1):
        lines.append(
            f"Run {index}: validation={run.validation_seconds:.6f} s; "
            f"reconciliation={run.reconciliation_seconds:.6f} s; "
            f"total={run.total_seconds:.6f} s"
        )
    for label, stats in (
        ("Validation", summary.validation),
        ("Reconciliation", summary.reconciliation),
        ("Total", summary.total),
    ):
        lines.append(
            f"{label}: min={stats.minimum:.6f} s; median={stats.median:.6f} s; "
            f"max={stats.maximum:.6f} s"
        )
    verdict = "PASS" if summary.target_met else "FAIL"
    lines.append(
        f"RNF-06 target (< {summary.target_seconds:.3f} s per run): {verdict}"
    )
    lines.append(f"Deterministic results: {summary.results_consistent}")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_TOTAL_ROWS)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument(
        "--target-seconds",
        type=float,
        default=DEFAULT_TARGET_SECONDS,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit stable-key JSON instead of the human-readable report.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark CLI and return a target-aware exit code."""

    arguments = _parser().parse_args(argv)
    try:
        summary = run_benchmark(
            total_rows=arguments.rows,
            runs=arguments.runs,
            target_seconds=arguments.target_seconds,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"Benchmark failed: {error}")
        return 2
    if arguments.json:
        print(json.dumps(summary.as_json_data(), indent=2, sort_keys=True))
    else:
        print(format_text_report(summary))
    return 0 if summary.target_met else 1


if __name__ == "__main__":
    raise SystemExit(main())
