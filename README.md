# KZ EcomOps Control Tower

Multi-channel order reconciliation and e-commerce operations analytics.

## Project status

**MVP complete — validation, reconciliation, local review, reporting and quality verification are implemented**

The completed MVP provides deterministic synthetic datasets, documented simulated exports for four platforms, canonical normalization, complete five-file validation, all ten reconciliation rules, explainable anomaly results, idempotent local SQLite persistence, an accessible Streamlit workflow, operational anomaly distributions, and spreadsheet-safe filtered CSV export. A clean Python 3.13 installation, the full automated suite, repository/history audit, headless Streamlit start, and the measured 100,000-row target have all been verified.

## The problem

E-commerce operations often span multiple sales channels and systems. Orders, payments, shipments, returns, and refunds may use different formats or contain inconsistent information, making manual checks slow and error-prone.

## Project objective

KZ EcomOps Control Tower normalizes synthetic multi-channel data into a common model and identifies operational or financial inconsistencies. This MVP focuses exclusively on order reconciliation.

## Implemented data pipeline

The current data pipeline includes:

- deterministic public sample datasets for valid, reconciliation, and intentionally invalid cases;
- documented simulated source exports for Shopify, WooCommerce, Amazon, and eBay;
- separate immutable mappings for source columns, statuses, identifiers, dates, and amounts;
- canonical normalization into the five required DataFrames without modifying source files or DataFrames;
- immutable schemas for the five required normalized CSV files;
- safe UTF-8 CSV reading, including optional UTF-8 BOM support;
- structural checks for headers, duplicate columns, field counts, and required columns;
- cell-level checks for required values, allowed values, monetary formats, limits, and timezone-aware ISO 8601 date-times;
- record-level integrity checks, including deterministic order identifiers, order-total arithmetic, and required status-dependent dates;
- blocking uniqueness checks for order, shipment, and return identifiers;
- non-blocking cross-file relationship findings for missing or inconsistent references;
- end-to-end directory validation with per-file and dataset-level counts and reports;
- transactional SQLite persistence with deterministic technical keys, source-row traceability, and idempotent re-imports;
- explicit reconciliation configuration with `Decimal("0.01")`, 48-hour shipping, and seven-day return-refund defaults;
- deterministic execution of `REC-01`–`REC-10` using an explicit timezone-aware reference time;
- immutable, explainable anomalies with protected compared values and source-record references;
- explicit `RuleNotEvaluated` results when a reliable conclusion cannot be reached;
- idempotent SQLite anomaly persistence with first/last detection timestamps and a review status that can be updated without changing source data.

Structural, value, integrity, and blocking uniqueness errors prevent the dataset from being marked ready for reconciliation. Relationship findings do not reject rows or block readiness: they remain attached to the report and are evaluated by `REC-10`.

Required shipment dates remain subject to status-dependent integrity checks. A shipped or delivered record without a tracking number is preserved for `REC-05` and does not block reconciliation readiness.

The pipeline never rewrites source CSV files, removes records, or converts monetary values to floating point. SQLite deliberately omits blocking cross-file foreign keys so orphan records remain available to `REC-10`.

## Required MVP data files

The Order Reconciliation MVP uses five required CSV files:

- `orders.csv`
- `payments.csv`
- `shipments.csv`
- `returns.csv`
- `refunds.csv`

All MVP monetary values use EUR. Files for order items, products, inventory, advertising, and traffic are reserved for later versions.

## Synthetic sample data

The public sample tree is organized as follows:

```text
data/sample/
├── normalized/valid/       # canonical valid four-platform dataset
├── scenarios/              # one five-CSV dataset for each REC-01–REC-10 case
├── invalid/                # read, value, integrity, and uniqueness failures
├── sources/                # simulated exports for the four platforms
├── manifest.json           # expected validation and REC outcomes
└── README.md
```

Check the committed sample files against the deterministic in-memory build without changing them:

```powershell
.\.venv\Scripts\python.exe -m kz_ecomops.sample_data data/sample --check
```

The files under `data/sample/sources/` are portfolio simulations created for this project. They must not be interpreted as official platform API or export contracts.

## Normalization and local storage

The public normalization API can process one simulated platform directory with `normalize_platform_exports()` or combine all four with `normalize_all_platforms()`. `write_canonical_csvs()` writes the five canonical DataFrames to a new directory without overwriting existing canonical files.

After `validate_dataset_directory()` returns a complete reconciliation-ready result, `persist_validated_dataset()` stores it transactionally in SQLite. `reconcile_dataset()` then runs all ten rules with an explicit reference time and optional `ReconciliationConfig`. `persist_reconciliation_result()` saves anomalies without resetting a manually updated review status. Re-importing identical canonical data or reconciliation results does not multiply records.

## Streamlit application

The Streamlit interface provides the complete non-technical MVP path after the application starts:

1. Upload exactly one copy of `orders.csv`, `payments.csv`, `shipments.csv`, `returns.csv`, and `refunds.csv`.
2. Validate the dataset and review processed, accepted, and rejected records.
3. Correct any blocking problems or review non-blocking relationship findings.
4. Set the explicit UTC reference date and time, monetary tolerance, shipping limit, return-refund limit, and optional high-delay threshold.
5. Run reconciliation only when validation reports `Ready for reconciliation`.
6. Review operational indicators, filter anomalies, inspect compared values and record references, and review checks that could not be evaluated.
7. Change an anomaly review status between `open`, `in_review`, `resolved`, and `dismissed`.
8. Compare complete and filtered anomaly distributions, then download exactly the currently filtered anomalies as CSV.

Uploaded CSV files are staged only in an automatically deleted temporary directory. They are never copied into the repository or retained by the application. Use only synthetic or explicitly authorized data; the MVP accepts EUR only.

Validated canonical records and reconciliation anomalies are stored locally in:

```text
.runtime/kz-ecomops-control-tower.sqlite3
```

The `.runtime/` directory and all SQLite files are ignored by Git. Reconciliation persistence is idempotent, and a saved review status survives a later reconciliation of the same anomaly.

## Operational reporting and CSV export

The anomaly dashboard shows deterministic counts for anomaly code, severity, platform, and review status. Each dimension is displayed for both the complete reconciliation result and the anomalies matching all current filters. A zero count is shown as zero; unavailable results remain explicitly marked as not calculated.

`Download filtered anomalies CSV` exports exactly the anomalies visible through the current combined filters, including updated review statuses. If the filters match no anomalies, the download remains a valid header-only CSV with zero data rows. The download is unavailable whenever there is no current reconciliation result, including after an upload or configuration change invalidates an older result.

The CSV is generated entirely in memory and never written to the repository or runtime directory. Its deterministic filename is derived from the result reference time:

```text
kz-ecomops-anomalies-YYYYMMDD-HHMMSSZ.csv
```

The file uses UTF-8 with a BOM for compatibility with common Windows spreadsheet installations. Text beginning with a spreadsheet formula marker is prefixed with an apostrophe, while JSON, ISO date-times, decimal money, and duration fields retain their unambiguous formats.

The immutable CSV column order is:

1. `anomaly_id`
2. `rule_code`
3. `anomaly_code`
4. `order_id`
5. `platform`
6. `problem_type`
7. `description`
8. `severity`
9. `detected_at`
10. `recommended_action`
11. `review_status`
12. `compared_values_json`
13. `record_references_json`
14. `reference_at`
15. `monetary_tolerance`
16. `currency`
17. `shipping_limit_hours`
18. `return_refund_limit_days`
19. `high_shipping_delay_threshold_hours`

## Implemented reconciliation rules

| Rule | Anomaly code | Condition | Severity | Recommended action |
|---|---|---|---|---|
| REC-01 | `PAYMENT_AMOUNT_MISMATCH` | Confirmed net payments differ from the order total beyond tolerance. | high | Compare order and provider transactions. |
| REC-02 | `PAID_NOT_SHIPPED_ON_TIME` | A fully paid, non-cancelled order has not shipped after the configured limit. | medium/high | Check inventory, warehouse blocks, and fulfillment. |
| REC-03 | `SHIPPED_WITHOUT_CONFIRMED_PAYMENT` | A shipment departed without sufficient confirmed net payment. | critical | Verify payment immediately and recover any shortfall. |
| REC-04 | `DUPLICATE_PAYMENT` | Payment or provider transaction identifiers are duplicated. | high | Confirm transactions before refunding a duplicate charge. |
| REC-05 | `SHIPMENT_WITHOUT_TRACKING` | A shipped or delivered shipment has blank tracking. | medium | Retrieve tracking from the carrier and update the channel. |
| REC-06 | `CANCELLED_ORDER_SHIPPED` | A cancelled order has a shipped or delivered shipment. | critical | Attempt to stop delivery and review payment/refund status. |
| REC-07 | `RETURN_RECEIVED_NOT_REFUNDED` | An overdue received return has no sufficient confirmed refund. | high | Complete or document the expected refund. |
| REC-08 | `REFUND_EXCEEDS_PAYMENT` | Confirmed refunds exceed confirmed net payments beyond tolerance. | critical | Stop further refunds and verify all transactions. |
| REC-09 | `DUPLICATE_REFUND` | Refund or provider refund identifiers are duplicated. | critical | Verify provider movements and prevent further credits. |
| REC-10 | `CROSS_SYSTEM_RECORD_MISSING` | Cross-file references or declared event records are missing or inconsistent. | high/critical | Check exports, identifier mapping, and synchronization. |

Money is always compared with `Decimal` and only within the same currency. A difference exactly equal to the configured tolerance does not create an anomaly. Time-based rules use only the explicit reference time supplied by the caller; the engine never reads the current clock implicitly.

## Technology stack

### Configured

- Python 3.13
- Pandas 3.0.5
- Streamlit 1.60.0
- pytest 9.1.1
- SQLite through Python's standard-library `sqlite3` module

No service, container, external database, credential, or network connection is
required during normal local use.

## Local setup

The project dependencies are declared in `pyproject.toml` and should be installed inside a local virtual environment.

### Windows

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### macOS and Linux

```bash
python3.13 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
```

The `.venv` directory must not be published or committed. It is recreated locally from the dependency information in `pyproject.toml`.

## Running the application

From the project root, start Streamlit with the virtual-environment interpreter.

### Windows

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### macOS and Linux

```bash
./.venv/bin/python -m streamlit run app.py
```

The browser interface can be used without further terminal commands. For a ready demonstration, upload the five files from `data/sample/normalized/valid/` or one complete directory under `data/sample/scenarios/`. Intentionally invalid examples under `data/sample/invalid/` demonstrate blocking reports.

## Quick demo

1. Start Streamlit from the repository root.
2. Upload the five files from `data/sample/normalized/valid/`, validate them and run reconciliation to demonstrate a real zero-anomaly result.
3. Refresh, then upload the five files from `data/sample/scenarios/rec-05-shipment-without-tracking/`.
4. Validate, run reconciliation, inspect the REC-05 anomaly, apply filters, update its review status and download the filtered CSV.

The complete timed walkthrough and safe runtime reset are documented in the
[interview demo guide](docs/DEMO_GUIDE.md).

## Running the tests

From the project root, run the complete automated suite with the virtual environment interpreter:

### Windows

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m scripts.audit_repository
.\.venv\Scripts\python.exe -m kz_ecomops.sample_data data/sample --check
```

### macOS and Linux

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m pip check
./.venv/bin/python -m scripts.audit_repository
./.venv/bin/python -m kz_ecomops.sample_data data/sample --check
```

The repository audit scans current tracked files and Git history. Its narrow
allowlist covers the project author, the GitHub noreply address, declared
synthetic CSV files under `data/sample/`, and authorized PNG screenshots under
`docs/assets/`; secret patterns are still checked inside allowlisted files.

The final verified suite contains **550 tests**. A fresh external Python 3.13.15
environment installed the project with `pip install -e ".[dev]"`, passed all 550
tests and `pip check`, confirmed the deterministic samples, and served Streamlit
1.60.0 with HTTP 200 before the process was stopped and its port released.

## Measured performance

The deterministic benchmark generates exactly 100,000 temporary EUR records,
runs one excluded warm-up and measures three complete validation/reconciliation
executions. The recorded pipeline totals were **8.055 s**, **8.087 s**, and
**8.125 s** (minimum/median/maximum), satisfying the less-than-30-second RNF-06
target. Generation is measured separately and temporary data is removed
automatically. See [Performance verification](docs/PERFORMANCE.md) for the
environment, stage timings and reproducible commands.

## Repository structure

```text
data/sample/              Deterministic public synthetic data
docs/                     Requirements, architecture, demo and evidence
scripts/                  Benchmark and repository audit tools
src/kz_ecomops/
  normalization/          Simulated platform exports to canonical data
  validation/             Safe five-file validation and relationship findings
  reconciliation/         Immutable domain and REC-01 through REC-10
  storage/                Idempotent transactional SQLite persistence
  reporting/              Distributions and in-memory CSV export
  ui/                     Thin Streamlit workflow and presentation
tests/                    Unit, integration, UI, benchmark and audit tests
app.py                    Streamlit entry point
pyproject.toml            Package metadata and pinned direct dependencies
```

## Architecture

The complete flow is upload → temporary staging → validation → reconciliation →
SQLite → review/reporting → in-memory CSV download. Business rules do not depend
on Streamlit, monetary calculations use `Decimal`, time rules use an explicit
reference, and stable anomaly identity is independent of row order. See the
[architecture guide](docs/ARCHITECTURE.md) for package boundaries, validation
stages, rule design, idempotency and trade-offs.

## Interface screenshots

No screenshots are committed in this revision. The installed browser-control
runtime was blocked by the Windows execution sandbox before it could open the
local app, and Playwright or Selenium were not already available. No dependency
was added and no mockup was substituted for a real capture. The UI remains
verified by Streamlit AppTest coverage and HTTP 200 headless starts in both the
project and clean environments; the [demo guide](docs/DEMO_GUIDE.md) reproduces
each intended screen with permanent synthetic samples.

## Known limits

- manual canonical CSV upload; no live or scheduled platform integration;
- EUR only, with no currency conversion;
- order-total reconciliation for partial shipment, return and refund cases;
- local single-user SQLite; no authentication, roles or shared cloud service;
- no full KPI dashboard, inventory optimization or item-level analysis;
- explicit reference time selected by the user rather than an implicit clock;
- human review is required before operational or financial action.

## Troubleshooting

- **`python` or `py` is not found:** install standard 64-bit CPython 3.13 from
  python.org, then close and reopen the terminal so Windows refreshes PATH.
- **The virtual environment is missing:** recreate `.venv` with the command in
  Local setup; do not commit it.
- **The app reports missing or duplicate files:** upload exactly one file with
  each required canonical filename.
- **Reconciliation is unavailable:** correct every blocking validation message;
  relationship findings are non-blocking and are evaluated by REC-10.
- **Port 8501 is already in use:** stop the previous Streamlit process or pass a
  different local port with `--server.port`.
- **A clean demo needs empty review state:** close Streamlit and follow the exact,
  non-recursive database reset procedure in `docs/DEMO_GUIDE.md`.

## Documentation

- [Project overview](docs/PROJECT_OVERVIEW.md)
- [Requirements](docs/REQUIREMENTS.md)
- [Data dictionary](docs/DATA_DICTIONARY.md)
- [MVP roadmap](docs/MVP_ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Interview demo guide](docs/DEMO_GUIDE.md)
- [Completion checklist](docs/COMPLETION_CHECKLIST.md)
- [Performance verification](docs/PERFORMANCE.md)

## Data policy

All data included in this public project is entirely synthetic. Real customer, company, transaction, credential, token, or API data must not be committed to the repository.

## Roadmap

1. Planning and repository setup — completed.
2. Python project configuration and dependency setup — completed.
3. CSV schemas and complete validation pipeline — completed.
4. Synthetic demonstration datasets — completed.
5. Data normalization and local SQLite storage — completed.
6. Order reconciliation engine — completed.
7. Streamlit user interface — completed.
8. CSV exports and operational reporting — completed in Phase 7.
9. Final testing, performance checks, audit, clean installation and documentation — completed in Phase 8.

KPI analytics, inventory optimization, real platform APIs, authentication, and cloud deployment are planned only for future versions.

## License

This project is released under the [MIT License](LICENSE).

## Introduzione in italiano

KZ EcomOps Control Tower è un MVP completo e riproducibile per il controllo operativo di un e-commerce multicanale. Include dati interamente sintetici, validazione, normalizzazione, tutte le regole `REC-01`–`REC-10`, persistenza SQLite idempotente, interfaccia Streamlit, distribuzioni operative ed esportazione CSV filtrata. Test, audit, installazione pulita e benchmark da 100.000 righe sono stati verificati e documentati; KPI avanzati e ottimizzazione dell'inventario restano sviluppi futuri.
