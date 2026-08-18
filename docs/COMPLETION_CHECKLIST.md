# MVP completion checklist

This checklist maps every numbered requirement and completion criterion to
verifiable repository evidence. The allowed status vocabulary is `satisfied`,
`not applicable`, and `blocked`. Phase 8 is not declared complete until the two
provisional clean-install/demo rows are changed from `blocked` after Checkpoint 4.

## Functional requirements

| Requirement | Status | Implementation | Test or proof | Reference / exclusion |
| --- | --- | --- | --- | --- |
| RF-01 | satisfied | Five-file schemas, upload staging and dataset orchestration. | `tests/validation/test_dataset.py`; `tests/ui/test_uploads.py` | [Data dictionary](DATA_DICTIONARY.md) |
| RF-02 | satisfied | Central `SUPPORTED_PLATFORMS`; four simulated mappings. | `test_supported_platforms_are_exact_and_used_by_every_schema`; `test_four_platform_exports_reach_idempotent_sqlite_storage` | [Architecture](ARCHITECTURE.md) |
| RF-03 | satisfied | Schema-driven required-header checks. | `test_reports_missing_required_column`; `test_schema_has_exact_required_columns` | [Data dictionary](DATA_DICTIONARY.md) |
| RF-04 | satisfied | Decimal and timezone-aware date validation. | `tests/validation/test_values.py` invalid decimal/date cases | [Architecture](ARCHITECTURE.md) |
| RF-05 | satisfied | Exact platform/status allowlists and EUR-only currency. | `test_allowed_value_comparison_is_case_sensitive`; `test_eur_is_the_only_supported_currency` | [Requirements](REQUIREMENTS.md) |
| RF-06 | satisfied | Per-file and dataset counts plus ordered messages in Streamlit. | `test_file_and_dataset_counts_are_consistent`; `tests/ui/test_app.py` | [Demo guide](DEMO_GUIDE.md) |
| RF-07 | satisfied | Blocking readiness gate; non-blocking duplicates/relationships retained. | `test_reports_structurally_invalid_header`; `test_relationship_finding_is_non_blocking_and_keeps_dataframes` | [Architecture](ARCHITECTURE.md) |
| RF-08 | satisfied | Immutable per-platform normalization mappings to canonical frames. | `tests/normalization/test_normalization.py`; integration data pipeline | [Architecture](ARCHITECTURE.md) |
| RF-09 | satisfied | `platform:source_order_id` integrity and uniqueness. | `test_reports_duplicate_platform_source_order_key`; integrity tests | [Data dictionary](DATA_DICTIONARY.md) |
| RF-10 | satisfied | ISO 8601 timezone preservation in normalization and validation. | normalization date tests; `test_accepts_supported_iso_datetimes` | [Architecture](ARCHITECTURE.md) |
| RF-11 | satisfied | Exact two-decimal EUR schema and `Decimal` calculations. | `test_all_mvp_decimal_columns_have_exactly_two_decimal_places`; reconciliation boundaries | [Requirements](REQUIREMENTS.md) |
| RF-12 | satisfied | Transactional canonical and anomaly SQLite APIs. | `tests/storage/test_sqlite.py`; `test_reconciliation_storage.py` | [Architecture](ARCHITECTURE.md) |
| RF-13 | satisfied | Deterministic keys and upserts for re-import/reconciliation. | `test_second_import_is_idempotent`; `test_second_persistence_is_idempotent` | [Architecture](ARCHITECTURE.md) |
| RF-14 | satisfied | UI enables reconciliation only after successful validation. | `test_valid_upload_validation_reconciliation_and_review_path`; invalid-state tests | [Demo guide](DEMO_GUIDE.md) |
| RF-15 | satisfied | Rule evaluators REC-01 through REC-10 and one engine. | `test_every_manifest_scenario_produces_exactly_one_expected_anomaly`; rule suites | [Architecture](ARCHITECTURE.md) |
| RF-16 | satisfied | Immutable tolerance and time-limit configuration exposed by UI. | config domain tests; `test_config_parses_decimal_directly_and_requires_valid_thresholds` | [Requirements](REQUIREMENTS.md) |
| RF-17 | satisfied | EUR-only rejection; no conversion or mixed-currency comparison. | schema/value tests; rule currency cases | [Architecture](ARCHITECTURE.md) |
| RF-18 | satisfied | Explicit reference time, stable IDs and sorted immutable results. | domain/engine reorder and repeatability tests | [Architecture](ARCHITECTURE.md) |
| RF-19 | satisfied | `ReconciliationAnomaly` stores every required field and references. | `test_anomaly_table_and_detail_include_accessible_severity_and_rf19_fields`; export tests | [Architecture](ARCHITECTURE.md) |
| RF-20 | satisfied | Central `Severity` enum with four exact values. | `test_public_enums_have_exact_values` | [Requirements](REQUIREMENTS.md) |
| RF-21 | satisfied | Central `ReviewStatus` enum with four exact values. | `test_public_enums_have_exact_values` | [Requirements](REQUIREMENTS.md) |
| RF-22 | satisfied | SQLite status update and UI adapter preserve source/results. | review status storage/UI tests | [Demo guide](DEMO_GUIDE.md) |
| RF-23 | satisfied | Combined platform/code/severity/status filters. | `test_no_filter_single_filter_combined_filter_and_zero_results`; app tests | [Demo guide](DEMO_GUIDE.md) |
| RF-24 | satisfied | Detail view exposes rule, compared values and references. | `test_anomaly_table_and_detail_include_accessible_severity_and_rf19_fields` | [Demo guide](DEMO_GUIDE.md) |
| RF-25 | satisfied | Filtered deterministic in-memory CSV download. | `tests/reporting/test_export.py`; `tests/ui/test_reporting.py` | README export section |
| RF-26 | satisfied | Operational summary shows orders, total value, payments, shipments, returns, refunds and anomalies. | `test_summary_distinguishes_not_calculated_from_real_zero`; app metrics tests | [Architecture](ARCHITECTURE.md) |
| RF-27 | satisfied | Complete and filtered distributions in all four dimensions. | `tests/reporting/test_distributions.py`; app distribution test | README reporting section |
| RF-28 | satisfied | `Not calculated` and `RuleNotEvaluated` remain distinct from zero. | presentation/app unavailable and zero tests | [Architecture](ARCHITECTURE.md) |

## Non-functional requirements

| Requirement | Status | Implementation | Test or proof | Reference / exclusion |
| --- | --- | --- | --- | --- |
| RNF-01 | satisfied | English UI/messages; development hand-off in simple Italian. | UI text tests and repository review | README |
| RNF-02 | satisfied | Business-named modules, typed immutable models and focused docstrings. | compileall; quality audit; code review | [Architecture](ARCHITECTURE.md) |
| RNF-03 | satisfied | Separate validation, normalization, reconciliation, storage, reporting and UI packages. | imports and package-specific suites | [Architecture](ARCHITECTURE.md) |
| RNF-04 | satisfied | Every REC evaluator runs without Streamlit. | `tests/reconciliation/` | [Architecture](ARCHITECTURE.md) |
| RNF-05 | satisfied | Positive, negative, boundary/missing and mutation cases for REC-01–REC-10. | rule suites and documented matrix | [Requirements](REQUIREMENTS.md) |
| RNF-06 | satisfied | Reproducible 100,000-row benchmark; maximum 8.125 seconds. | `tests/benchmark/`; full benchmark on 2026-08-18 | [Performance](PERFORMANCE.md) |
| RNF-07 | satisfied | Readers, validators, rules and reporting do not mutate source CSV/DataFrames. | mutation tests across validation/reconciliation/reporting | [Architecture](ARCHITECTURE.md) |
| RNF-08 | satisfied | Deterministic synthetic-only public data and real-data audit. | sample manifest check; repository/history audit PASS | `data/sample/README.md` |
| RNF-09 | satisfied | No credential flow; secret patterns audited and redacted. | `tests/audit/`; complete audit PASS | README data policy |
| RNF-10 | blocked | Portable `pathlib`, standard venv and OS-specific commands are present. | Final external clean-install/headless proof pending Checkpoint 4. | README setup |
| RNF-11 | satisfied | Python range and exact runtime/dev dependencies in `pyproject.toml`. | `pip check`; editable install in current environment | README setup |
| RNF-12 | satisfied | Rule code plus current source file, row and record identifiers. | domain, engine, storage reorder and export-reference tests | [Architecture](ARCHITECTURE.md) |
| RNF-13 | satisfied | Structured codes and actionable file/row/column messages. | reader/value/integrity/dataset error tests | [Architecture](ARCHITECTURE.md) |
| RNF-14 | satisfied | Severity and availability use visible text/symbols, not color alone. | UI presentation and app tests | [Demo guide](DEMO_GUIDE.md) |
| RNF-15 | satisfied | Enums, schemas and `ReconciliationConfig` centralize states, codes and thresholds. | exact enum/schema/config tests | [Architecture](ARCHITECTURE.md) |
| RNF-16 | satisfied | Small phase-linked conventional commits and dedicated branches. | Git history audit and log | [MVP roadmap](MVP_ROADMAP.md) |
| RNF-17 | satisfied | English package, function, column and folder names. | repository audit/review | [Architecture](ARCHITECTURE.md) |
| RNF-18 | satisfied | Required first lines, English main text and final Italian introduction. | README review | README |
| RNF-19 | satisfied | Standard MIT text for Klaus Zanaj, 2026. | `LICENSE`; repository audit | [License](../LICENSE) |

## Completion criteria 6.1 — Functions

| Criterion | Status | Implementation | Test or proof | Reference / exclusion |
| --- | --- | --- | --- | --- |
| 6.1-1 Five required CSV files load and validate | satisfied | Upload and dataset validation pipeline. | dataset and UI workflow suites | [Demo guide](DEMO_GUIDE.md) |
| 6.1-2 Optional future CSV files are not required | satisfied | Registry contains exactly five MVP schemas. | `test_optional_csv_file_is_not_registered` | [Requirements](REQUIREMENTS.md) |
| 6.1-3 Four channels represented | satisfied | Four deterministic source mappings and samples. | four-platform integration test | `data/sample/README.md` |
| 6.1-4 Valid data normalized and saved | satisfied | Normalization plus transactional SQLite storage. | `test_four_platform_exports_reach_idempotent_sqlite_storage` | [Architecture](ARCHITECTURE.md) |
| 6.1-5 REC-01–REC-10 implemented | satisfied | Ten pure rule evaluators. | manifest and rule suites | [Architecture](ARCHITECTURE.md) |
| 6.1-6 RF-19 anomaly fields complete | satisfied | Immutable anomaly model and detail/export adapters. | domain, presentation and export tests | [Architecture](ARCHITECTURE.md) |
| 6.1-7 Filters, detail, status and export work | satisfied | Streamlit/reporting/storage workflow. | UI and reporting suites | [Demo guide](DEMO_GUIDE.md) |
| 6.1-8 Zero differs from unavailable | satisfied | `Not calculated` and `RuleNotEvaluated`. | UI presentation tests | [Architecture](ARCHITECTURE.md) |

## Completion criteria 6.2 — Quality

| Criterion | Status | Implementation | Test or proof | Reference / exclusion |
| --- | --- | --- | --- | --- |
| 6.2-1 Valid and anomalous synthetic data for every REC | satisfied | Valid dataset plus ten permanent scenario directories. | sample-data and documented-matrix tests | `data/sample/README.md` |
| 6.2-2 RNF-05 tests pass | satisfied | Dedicated rule suites. | complete pytest suite | [Requirements](REQUIREMENTS.md) |
| 6.2-3 Same inputs and reference produce same results | satisfied | Deterministic IDs/order/configuration. | engine/domain reorder tests | [Architecture](ARCHITECTURE.md) |
| 6.2-4 Useful invalid-column/type and REC-10 behavior | satisfied | Blocking messages plus retained relationship findings. | dataset, reader, value and REC-10 tests | [Architecture](ARCHITECTURE.md) |
| 6.2-5 No real data, secrets or credentials | satisfied | Synthetic-only policy and current/history audit. | audit PASS | README data policy |
| 6.2-6 RNF-06 measured | satisfied | 100,000-row benchmark. | maximum 8.125 seconds | [Performance](PERFORMANCE.md) |
| 6.2-7 Installation, start, samples, rules and limits documented | satisfied | README plus architecture/demo/performance docs. | documentation review | [Demo guide](DEMO_GUIDE.md) |

## Completion criteria 6.3 — Final demonstration

| Criterion | Status | Implementation | Test or proof | Reference / exclusion |
| --- | --- | --- | --- | --- |
| 6.3-1 Prepare environment | blocked | Copyable Windows/macOS/Linux commands documented. | External clean-install proof pending Checkpoint 4. | README setup |
| 6.3-2 Start application | blocked | Module-based Streamlit command documented. | Clean-environment HTTP 200 pending Checkpoint 4. | README running section |
| 6.3-3 Load demonstration files | satisfied | Exact permanent sample directories and five-file uploader. | UI upload and AppTest workflow tests | [Demo guide](DEMO_GUIDE.md) |
| 6.3-4 Run reconciliation | satisfied | Validation gate and explicit run control. | UI workflow and AppTest reconciliation tests | [Demo guide](DEMO_GUIDE.md) |
| 6.3-5 Understand an anomaly | satisfied | Plain description/action, rule, compared values and references. | presentation tests; REC-05 walkthrough | [Demo guide](DEMO_GUIDE.md) |
| 6.3-6 Filter and update review status | satisfied | Combined filters and persisted status control. | UI, reporting and storage tests | [Demo guide](DEMO_GUIDE.md) |
| 6.3-7 Export result | satisfied | Filtered in-memory download. | export and UI tests | [Demo guide](DEMO_GUIDE.md) |

## Current totals

- Satisfied: 66
- Not applicable: 0
- Blocked pending Checkpoint 4: 3 (`RNF-10`, `6.3-1`, `6.3-2`)
