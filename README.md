# KZ EcomOps Control Tower

Multi-channel order reconciliation and e-commerce operations analytics.

## Project status

**Phase 2 complete: normalized CSV validation pipeline implemented**

The project now provides a tested validation layer for the five normalized MVP CSV files. It reads complete dataset directories, applies structural and data-quality checks in a deterministic order, and produces uniform immutable reports. The reconciliation rules and user interface are not implemented yet.

## The problem

E-commerce operations often span multiple sales channels and systems. Orders, payments, shipments, returns, and refunds may use different formats or contain inconsistent information, making manual checks slow and error-prone.

## Project objective

KZ EcomOps Control Tower aims to normalize synthetic multi-channel data into a common model and identify operational or financial inconsistencies. The first MVP module will focus exclusively on order reconciliation.

## Implemented validation

The current validation pipeline includes:

- immutable schemas for the five required normalized CSV files;
- safe UTF-8 CSV reading, including optional UTF-8 BOM support;
- structural checks for headers, duplicate columns, field counts, and required columns;
- cell-level checks for required values, allowed values, monetary formats, limits, and timezone-aware ISO 8601 date-times;
- record-level integrity checks, including deterministic order identifiers, order-total arithmetic, and status-dependent fields;
- blocking uniqueness checks for order, shipment, and return identifiers;
- non-blocking cross-file relationship findings for missing or inconsistent references;
- end-to-end directory validation with per-file and dataset-level counts and reports.

Structural, value, integrity, and blocking uniqueness errors prevent the dataset from being marked ready for reconciliation. Relationship findings do not reject rows or block readiness: they remain attached to the report for the future `REC-10` reconciliation rule.

The validator never rewrites source CSV files or removes records. Platform-specific source normalization, permanent demonstration datasets, database storage, and reconciliation logic remain future work.

## Required MVP data files

The Order Reconciliation MVP will require five CSV files:

- `orders.csv`
- `payments.csv`
- `shipments.csv`
- `returns.csv`
- `refunds.csv`

All MVP monetary values will use EUR. Files for order items, products, inventory, advertising, and traffic are reserved for later versions.

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

### Planned for future phases

- SQLite
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
4. Synthetic demonstration datasets — next phase.
5. Data normalization and local SQLite storage.
6. Order reconciliation engine.
7. Streamlit user interface.
8. CSV exports and operational reporting.
9. Testing, performance checks, and final documentation.

KPI analytics, inventory optimization, real platform APIs, authentication, and cloud deployment are planned only for future versions.

## License

This project is intended to be released under the [MIT License](LICENSE).

## Introduzione in italiano

KZ EcomOps Control Tower è un progetto dimostrativo per il controllo operativo di un e-commerce multicanale. La pipeline di validazione dei cinque CSV normalizzati è ora implementata e testata: distingue gli errori bloccanti dai problemi di relazione che saranno analizzati dalla futura riconciliazione. Il prossimo passo sarà creare dati dimostrativi interamente sintetici; le regole `REC-01`–`REC-10`, SQLite e l'interfaccia Streamlit non sono ancora implementati.
