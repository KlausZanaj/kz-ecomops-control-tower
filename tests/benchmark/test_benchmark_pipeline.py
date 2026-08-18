"""Reduced deterministic tests for the 100k-row benchmark tool."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.benchmark_pipeline import (
    BENCHMARK_FILENAMES,
    BenchmarkRun,
    dataset_digests,
    main,
    rows_per_file,
    run_benchmark,
    summarize_benchmark,
    write_benchmark_dataset,
)


def _run(total_seconds: float) -> BenchmarkRun:
    return BenchmarkRun(
        validation_seconds=total_seconds * 0.75,
        reconciliation_seconds=total_seconds * 0.25,
        total_seconds=total_seconds,
        total_rows=50,
        accepted_rows=50,
        rejected_rows=0,
        anomaly_count=0,
        not_evaluated_count=0,
        reconciliation_ready=True,
    )


def test_dataset_has_exact_counts_and_deterministic_bytes(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_counts = write_benchmark_dataset(first, 50)
    second_counts = write_benchmark_dataset(second, 50)

    assert rows_per_file(50) == 10
    assert first_counts == second_counts == {
        filename: 10 for filename in BENCHMARK_FILENAMES
    }
    assert sum(first_counts.values()) == 50
    assert dataset_digests(first) == dataset_digests(second)
    for filename in BENCHMARK_FILENAMES:
        assert len((first / filename).read_text(encoding="utf-8").splitlines()) == 11


def test_small_benchmark_is_ready_anomaly_free_and_cleans_temp_directory(
    tmp_path: Path,
) -> None:
    summary = run_benchmark(
        total_rows=50,
        runs=3,
        target_seconds=30,
        temporary_parent=tmp_path,
    )

    assert summary.total_rows == 50
    assert len(summary.measured_runs) == 3
    assert summary.results_consistent
    assert summary.target_met
    assert all(run.reconciliation_ready for run in summary.measured_runs)
    assert all(run.accepted_rows == 50 for run in summary.measured_runs)
    assert all(run.rejected_rows == 0 for run in summary.measured_runs)
    assert all(run.anomaly_count == 0 for run in summary.measured_runs)
    assert all(run.not_evaluated_count == 0 for run in summary.measured_runs)
    assert tuple(tmp_path.iterdir()) == ()


def test_timing_statistics_and_strict_target_verdict() -> None:
    warm_up = _run(9)
    runs = (_run(1), _run(3), _run(2))

    passing = summarize_benchmark(
        total_rows=50,
        rows_by_file={filename: 10 for filename in BENCHMARK_FILENAMES},
        generation_seconds=0.5,
        warm_up=warm_up,
        measured_runs=runs,
        target_seconds=3.1,
    )
    failing = summarize_benchmark(
        total_rows=50,
        rows_by_file={filename: 10 for filename in BENCHMARK_FILENAMES},
        generation_seconds=0.5,
        warm_up=warm_up,
        measured_runs=runs,
        target_seconds=3.0,
    )

    assert passing.total.minimum == 1
    assert passing.total.median == 2
    assert passing.total.maximum == 3
    assert passing.target_met
    assert not failing.target_met


def test_json_cli_is_parseable_and_reports_target_aware_exit_code(capsys) -> None:
    exit_code = main(
        ("--rows", "50", "--runs", "3", "--target-seconds", "30", "--json")
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["schema_version"] == 1
    assert output["total_rows"] == 50
    assert output["warm_up_excluded"] is True
    assert output["target_met"] is True
