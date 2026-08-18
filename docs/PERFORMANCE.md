# Performance verification

This document records a real, reproducible measurement of the complete KZ
EcomOps validation and reconciliation pipeline. The benchmark data is entirely
synthetic and is removed automatically after every execution.

## Result

RNF-06 is satisfied on the measured personal-computer environment. All three
measured executions completed the 100,000-row pipeline in less than 30 seconds;
the slowest execution took **8.125 seconds**.

| Item | Measured value |
| --- | --- |
| Date | 2026-08-18 |
| Source revision | Phase 8 performance commit based on `4812b85d41d637d497a68c8029c526b4dfed5dd9` |
| Operating system | Windows 11, build 26200, 64 bit |
| Python | CPython 3.13.15, 64 bit |
| Processor | AMD64 Family 25 Model 33 |
| Measured runs | 3, after 1 excluded warm-up |
| Required target | Complete pipeline in less than 30 seconds |
| Verdict | **PASS** |

## Dataset

The benchmark creates exactly 100,000 canonical records in a temporary
directory:

| File | Rows |
| --- | ---: |
| `orders.csv` | 20,000 |
| `payments.csv` | 20,000 |
| `shipments.csv` | 20,000 |
| `returns.csv` | 20,000 |
| `refunds.csv` | 20,000 |
| **Total** | **100,000** |

Every record is deterministic, synthetic, EUR-only, internally consistent and
free of intentional anomalies. Each measured run accepted 100,000 rows, rejected
zero rows, produced zero anomalies and returned a reconciliation-ready result.

## Timings

Times are measured with `time.perf_counter()`.

| Run | Validation | Reconciliation | Pipeline total |
| --- | ---: | ---: | ---: |
| 1 | 5.958 s | 2.097 s | 8.055 s |
| 2 | 5.966 s | 2.120 s | 8.087 s |
| 3 | 6.006 s | 2.119 s | 8.125 s |

| Statistic | Validation | Reconciliation | Pipeline total |
| --- | ---: | ---: | ---: |
| Minimum | 5.958 s | 2.097 s | 8.055 s |
| Median | 5.966 s | 2.119 s | 8.087 s |
| Maximum | 6.006 s | 2.120 s | 8.125 s |

Synthetic CSV generation took 0.483 seconds and is reported separately. It is
not included in the pipeline total.

## Measurement boundary

The validation measurement includes reading all five CSV files, structural and
cell-value validation, record-integrity and uniqueness validation, cross-file
relationship checks, and creation of the validation report. The reconciliation
measurement includes construction of the immutable reconciliation indexes and
execution of REC-01 through REC-10. The total is validation plus reconciliation.

The measurement excludes synthetic CSV generation, the non-counted warm-up,
Streamlit rendering, SQLite persistence and export generation. Temporary input
files are removed when the benchmark exits, including after an exception.

## Reproduce the benchmark

From the repository root, with the project virtual environment already created
and dependencies installed:

```powershell
& ".\.venv\Scripts\python.exe" -m scripts.benchmark_pipeline --rows 100000 --runs 3 --target-seconds 30
```

For machine-readable output:

```powershell
& ".\.venv\Scripts\python.exe" -m scripts.benchmark_pipeline --rows 100000 --runs 3 --target-seconds 30 --json
```

The command exits with a non-zero status when any measured execution reaches or
exceeds the requested target, when results differ between executions, or when
the pipeline is not reconciliation-ready.
