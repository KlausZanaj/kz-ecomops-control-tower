# KZ EcomOps Control Tower

Multi-channel order reconciliation and e-commerce operations analytics.

## Project status

**Python project structure and development environment configured**

This repository contains the approved project documentation, the initial package structure, and a reproducible Python development environment. The application logic is not implemented or operational yet.

## The problem

E-commerce operations often span multiple sales channels and systems. Orders, payments, shipments, returns, and refunds may use different formats or contain inconsistent information, making manual checks slow and error-prone.

## Project objective

KZ EcomOps Control Tower aims to normalize synthetic multi-channel data into a common model and identify operational or financial inconsistencies. The first MVP module will focus exclusively on order reconciliation.

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

## Documentation

- [Project overview](docs/PROJECT_OVERVIEW.md)
- [Requirements](docs/REQUIREMENTS.md)
- [Data dictionary](docs/DATA_DICTIONARY.md)
- [MVP roadmap](docs/MVP_ROADMAP.md)

## Data policy

All data included in this public project will be entirely synthetic. Real customer, company, transaction, credential, token, or API data must not be committed to the repository.

## Roadmap

1. Planning and repository setup — completed.
2. Python project configuration and dependency setup — current phase.
3. CSV schemas and data validation.
4. Synthetic test datasets.
5. Data normalization and local SQLite storage.
6. Order reconciliation engine.
7. Streamlit user interface.
8. CSV exports and operational reporting.
9. Testing, performance checks, and final documentation.

KPI analytics, inventory optimization, real platform APIs, authentication, and cloud deployment are planned only for future versions.

## License

This project is intended to be released under the [MIT License](LICENSE).

## Introduzione in italiano

KZ EcomOps Control Tower è un progetto dimostrativo per il controllo operativo di un e-commerce multicanale. La struttura Python e l’ambiente di sviluppo sono configurati, ma la logica aziendale non è stata ancora implementata. La prima versione confronterà ordini, pagamenti, spedizioni, resi e rimborsi utilizzando esclusivamente dati sintetici.
