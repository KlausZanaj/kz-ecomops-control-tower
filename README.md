# KZ EcomOps Control Tower

Multi-channel order reconciliation and e-commerce operations analytics.

## Project status

**Phase 6 complete: Streamlit reconciliation and review interface implemented**

The project now provides deterministic synthetic datasets, documented simulated exports for four platforms, canonical normalization, complete five-file validation, all ten reconciliation rules, explainable anomaly results, idempotent local SQLite persistence, and an accessible Streamlit workflow. Filtered CSV export is not implemented yet and remains planned for Phase 7.

## The problem

E-commerce operations often span multiple sales channels and systems. Orders, payments, shipments, returns, and refunds may use different formats or contain inconsistent information, making manual checks slow and error-prone.

## Project objective

KZ EcomOps Control Tower aims to normalize synthetic multi-channel data into a common model and identify operational or financial inconsistencies. The first MVP module will focus exclusively on order reconciliation.

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

Structural, value, integrity, and blocking uniqueness errors prevent the dataset from being marked ready for reconciliation. Relationship findings do not reject rows or block readiness: they remain attached to the report for the future `REC-10` reconciliation rule.

Required shipment dates remain subject to status-dependent integrity checks. A shipped or delivered record without a tracking number is preserved for the future `REC-05` rule and does not block reconciliation readiness.

The pipeline never rewrites source CSV files, removes records, or converts monetary values to floating point. SQLite deliberately omits blocking cross-file foreign keys so orphan records remain available for the future `REC-10` rule.

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
├── manifest.json           # expected validation and future REC outcomes
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

Uploaded CSV files are staged only in an automatically deleted temporary directory. They are never copied into the repository or retained by the application. Use only synthetic or explicitly authorized data; the MVP accepts EUR only.

Validated canonical records and reconciliation anomalies are stored locally in:

```text
.runtime/kz-ecomops-control-tower.sqlite3
```

The `.runtime/` directory and all SQLite files are ignored by Git. Reconciliation persistence is idempotent, and a saved review status survives a later reconciliation of the same anomaly.

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

### Planned for future phases

- Plotly

Additional technologies will be considered only after the MVP works and a clear need has been identified.

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

Current MVP limits remain explicit: no real platform integrations, authentication, cloud deployment, item-level partial-order reconciliation, or CSV anomaly export. Filtered CSV export is scheduled for Phase 7.

## Running the tests

From the project root, run the complete automated suite with the virtual environment interpreter:

### Windows

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

### macOS and Linux

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m pip check
```

## Documentation

- [Project overview](docs/PROJECT_OVERVIEW.md)
- [Requirements](docs/REQUIREMENTS.md)
- [Data dictionary](docs/DATA_DICTIONARY.md)
- [MVP roadmap](docs/MVP_ROADMAP.md)

## Data policy

All data included in this public project will be entirely synthetic. Real customer, company, transaction, credential, token, or API data must not be committed to the repository.

## Roadmap

1. Planning and repository setup — completed.
2. Python project configuration and dependency setup — completed.
3. CSV schemas and complete validation pipeline — completed.
4. Synthetic demonstration datasets — completed.
5. Data normalization and local SQLite storage — completed.
6. Order reconciliation engine — completed.
7. Streamlit user interface — completed.
8. CSV exports and operational reporting — planned for Phase 7.
9. Testing, performance checks, and final documentation.

KPI analytics, inventory optimization, real platform APIs, authentication, and cloud deployment are planned only for future versions.

## License

This project is intended to be released under the [MIT License](LICENSE).

## Introduzione in italiano

KZ EcomOps Control Tower è un progetto dimostrativo per il controllo operativo di un e-commerce multicanale. Sono ora disponibili dati interamente sintetici, validazione, normalizzazione, tutte le regole `REC-01`–`REC-10`, persistenza SQLite idempotente e un'interfaccia Streamlit completa per caricare i cinque CSV, eseguire la riconciliazione e aggiornare lo stato delle anomalie. L'esportazione CSV finale non è ancora implementata ed è prevista nella Fase 7.
