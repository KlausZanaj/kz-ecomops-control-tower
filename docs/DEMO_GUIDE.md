# Interview demo guide

This guide presents the completed local MVP in approximately 5–8 minutes using
only the permanent synthetic samples in `data/sample/`.

## Before the interview

From the repository root, create the environment and start the app:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

For macOS or Linux, use `python3.13`, `./.venv/bin/python`, and the same module
commands. Open the local URL printed by Streamlit. No credential or network
connection is required after installation.

### Safe runtime reset

Close Streamlit before resetting. Delete only the exact file
`.runtime/kz-ecomops-control-tower.sqlite3` from this repository. First display and
verify the resolved target; never run a recursive deletion against `.runtime`, the
repository root, a home directory or an unresolved variable.

```powershell
$runtimeDatabase = [System.IO.Path]::GetFullPath(
    (Join-Path (Get-Location) ".runtime\kz-ecomops-control-tower.sqlite3")
)
Write-Output "Verify exact database target: $runtimeDatabase"
if (Test-Path -LiteralPath $runtimeDatabase) {
    Remove-Item -LiteralPath $runtimeDatabase
}
```

The operation is recoverable only from a prior backup; it intentionally removes
saved review statuses as well as imported runtime data.

## 5–8 minute walkthrough

### 0:00–0:45 — Problem and architecture

Explain that multi-channel orders, payments, shipments, returns and refunds often
disagree. The application stages five uploads temporarily, validates them,
evaluates ten deterministic rules, persists results in local SQLite, and provides
review and export workflows. Business rules are independent of Streamlit.

### 0:45–1:45 — Valid dataset and validation

Upload all five files from `data/sample/normalized/valid/` and select **Validate
dataset**. Point out:

- all five required filenames are present;
- processed, accepted and rejected counts are explicit;
- the result says **Ready for reconciliation**;
- the database path shown is relative and uploads are not retained.

Select **Run reconciliation**. The valid sample produces zero anomalies. Use this
to show that real zero is distinct from **Not calculated** before a run.

### 1:45–3:30 — Explain a deterministic anomaly

Refresh the page, then upload the five files from
`data/sample/scenarios/rec-05-shipment-without-tracking/`. REC-05 is recommended
for an interview because it has no confusing time boundary: the shipment is
already `shipped` or `delivered`, while `tracking_number` is blank.

Validate and run reconciliation. Select the anomaly and show:

- `REC-05` / `SHIPMENT_WITHOUT_TRACKING`;
- medium severity as text, not color alone;
- the plain-English description and recommended action;
- compared values and source record references;
- unchanged blank tracking in the underlying validated data.

REC-10 is a useful alternative: use
`data/sample/scenarios/rec-10-cross-system-record-missing/` to explain why a
relationship finding is non-blocking during validation and becomes a traceable
business anomaly during reconciliation.

### 3:30–4:45 — Filters and operational distributions

Use platform, anomaly code, severity and review-status filters. Explain that they
combine, the filtered count and distributions update together, and a zero result
is a true zero. The full-result distributions remain visible for comparison.

### 4:45–5:30 — Review workflow

Open **Anomaly detail**, change **Review status** from `open` to `in_review` or
`resolved`, and save. Explain that only SQLite anomaly review metadata changes;
uploaded CSV content and immutable business results are not rewritten. Re-running
the same reconciliation preserves the saved status.

### 5:30–6:15 — Export

Choose **Download filtered anomalies CSV**. The export contains exactly the
current filtered set, its review statuses, deterministic identifiers, compared
values, record references and the configuration used for the run. It is generated
in memory with a UTF-8 BOM and spreadsheet-formula protection.

### 6:15–7:15 — Engineering evidence

Show `docs/ARCHITECTURE.md`, `docs/PERFORMANCE.md` and the test command. Summarize
the measured 100,000-row result (maximum 8.125 seconds against a 30-second target),
deterministic sample check, repository/history audit, and clean-install check.

### 7:15–8:00 — Limits and next steps

State the limits directly: manual synthetic CSV upload, local single-user SQLite,
EUR only, order-total rather than item-level partial reconciliation, no live APIs,
authentication, cloud deployment, full KPI suite or inventory optimization.
Future work should start with real integration requirements, not extra framework
complexity.

## Likely interview questions

| Question | Short technical answer |
| --- | --- |
| Why not detect missing tracking during validation? | It is a valid, analyzable business state. Blocking it would prevent REC-05 from producing an operational anomaly. |
| How is determinism achieved? | Explicit reference time, immutable configuration, stable iteration, Decimal arithmetic and anomaly IDs based on business identity rather than row position. |
| Why can orphan records enter SQLite? | REC-10 needs to preserve and inspect missing cross-system relationships; strict cross-file foreign keys would discard the evidence. |
| What happens when a rule cannot conclude safely? | It returns `RuleNotEvaluated` with a reason and references instead of guessing or returning zero. |
| Why SQLite? | It provides transactional, zero-service local persistence suitable for a portfolio MVP; a shared multi-user service is explicitly out of scope. |
| Can duplicate imports multiply records? | No. Canonical and anomaly keys are deterministic, and upserts are tested for idempotency, including reordered rows. |
| Does Streamlit contain rule logic? | No. It coordinates public validation, reconciliation, storage and reporting APIs and renders immutable results. |
| How are monetary errors avoided? | Canonical values use exact two-decimal strings and business calculations use `Decimal`; currencies are never converted or mixed. |
| Is the CSV safe for spreadsheets? | The export uses UTF-8 BOM, fixed columns and neutralizes text cells beginning with formula markers. |
| What would you productionize first? | Confirm real export/API contracts, security and multi-user requirements, then choose scheduling, authentication and shared storage accordingly. |
