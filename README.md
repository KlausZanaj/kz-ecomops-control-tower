# KZ EcomOps Control Tower

Multi-channel order reconciliation and e-commerce operations analytics.

## Project status

**Phases 3 and 4 complete: synthetic data, normalization, and SQLite persistence implemented**

The project now provides deterministic synthetic datasets, documented simulated exports for four platforms, canonical normalization, complete five-file validation, and idempotent local SQLite persistence. The `REC-01`–`REC-10` reconciliation engine and Streamlit user interface are not implemented yet.

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
- transactional SQLite persistence with deterministic technical keys, source-row traceability, and idempotent re-imports.

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

After `validate_dataset_directory()` returns a complete reconciliation-ready result, `persist_validated_dataset()` stores it transactionally in SQLite. Re-importing the same result reports records as already present instead of multiplying them. Exact payment and refund duplicates inside the first import remain distinct for the future `REC-04` and `REC-09` rules.

## Planned reconciliation checks

The MVP is planned to detect:

1. payment amount different from the order total;
2. paid order not shipped within the configured time limit;
3. order shipped without confirmed payment;
4. duplicate payment;
5. shipment without a tracking number;
6. cancelled order that was still shipped;
7. received return not refunded within the configured time limit;
8. refund greater than the confirmed payment amount;
9. duplicate refund;
10. order-related record present in one system but missing from another.

## Technology stack

### Configured

- Python 3.13
- Pandas 3.0.5
- pytest 9.1.1
- SQLite through Python's standard-library `sqlite3` module

### Planned for future phases

- Streamlit
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
6. Order reconciliation engine — next phase.
7. Streamlit user interface.
8. CSV exports and operational reporting.
9. Testing, performance checks, and final documentation.

KPI analytics, inventory optimization, real platform APIs, authentication, and cloud deployment are planned only for future versions.

## License

This project is intended to be released under the [MIT License](LICENSE).

## Introduzione in italiano

KZ EcomOps Control Tower è un progetto dimostrativo per il controllo operativo di un e-commerce multicanale. Sono ora disponibili dati interamente sintetici e deterministici, export simulati per quattro piattaforme, normalizzazione nei cinque CSV comuni e salvataggio locale idempotente in SQLite. Le regole `REC-01`–`REC-10` e l'interfaccia Streamlit non sono ancora implementate; il prossimo passo è il motore di riconciliazione.
