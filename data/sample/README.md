# Synthetic sample data

Every identifier, amount, timestamp, and descriptive value in this directory is deterministic and invented for this public portfolio project. The four platform names identify the simulated source being demonstrated; the files are not official API or export contracts.

## Structure

- `normalized/valid/`: canonical five-file dataset covering Shopify, WooCommerce, Amazon, and eBay without blocking errors or relationship findings.
- `scenarios/`: ten isolated five-file datasets, one for each implemented `REC-01`–`REC-10` rule.
- `invalid/`: separate five-file datasets that intentionally fail read, value, integrity, or uniqueness validation.
- `sources/<platform>/`: simulated source exports used by the normalization examples.
- `manifest.json`: machine-readable expected validation and anomaly outcomes.

All monetary values are EUR. Canonical timestamps use timezone-aware ISO 8601 strings and canonical order identifiers use `platform:source_order_id`.

## Verification

From the project root, check that the committed files match the deterministic generator without writing anything:

```powershell
.\.venv\Scripts\python.exe -m kz_ecomops.sample_data data/sample --check
```

The deterministic reconciliation engine implements `REC-01`–`REC-10`. Each scenario validates successfully and produces exactly the anomaly documented in the manifest when reconciled with its declared reference time.
