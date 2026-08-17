"""Deterministic synthetic datasets used by the public portfolio project."""

from __future__ import annotations

import argparse
import csv
import io
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .validation import CSV_SCHEMAS, DataType


PLATFORMS = ("shopify", "woocommerce", "amazon", "ebay")
SOURCE_PREFIXES = MappingProxyType(
    {"shopify": "sh", "woocommerce": "wc", "amazon": "amz", "ebay": "eb"}
)
_MANAGED_TEXT_SUFFIXES = frozenset({".csv", ".json", ".md"})

_SOURCE_ALIASES = MappingProxyType(
    {
        "source_order_id": "order_ref",
        "order_number": "order_number",
        "ordered_at": "ordered_time",
        "order_status": "order_state",
        "payment_status": "financial_state",
        "fulfillment_status": "fulfillment_state",
        "currency": "currency_code",
        "subtotal": "subtotal_amount",
        "discount_total": "discount_amount",
        "shipping_total": "shipping_amount",
        "tax_total": "tax_amount",
        "order_total": "total_amount",
        "customer_country": "country_code",
        "cancelled_at": "cancelled_time",
        "cancellation_reason": "cancel_reason",
        "updated_at": "updated_time",
        "payment_id": "payment_ref",
        "provider_transaction_id": "provider_transaction_ref",
        "payment_method": "payment_method",
        "amount": "amount_value",
        "paid_at": "paid_time",
        "created_at": "created_time",
        "shipment_id": "shipment_ref",
        "shipment_status": "shipment_state",
        "carrier": "carrier_name",
        "shipping_service": "service_name",
        "tracking_number": "tracking_ref",
        "shipped_at": "shipped_time",
        "delivered_at": "delivered_time",
        "warehouse_id": "warehouse_ref",
        "return_id": "return_ref",
        "return_status": "return_state",
        "return_reason": "return_reason",
        "requested_at": "requested_time",
        "received_at": "received_time",
        "expected_refund_amount": "expected_refund_value",
        "refund_id": "refund_ref",
        "provider_refund_id": "provider_refund_ref",
        "refund_status": "refund_state",
        "reason": "refund_reason",
        "refunded_at": "refunded_time",
    }
)

_SOURCE_STATUS_VALUES = MappingProxyType(
    {
        "shopify": MappingProxyType(
            {
                ("order_status", "completed"): "closed",
                ("payment_status", "refunded"): "refunded",
                ("fulfillment_status", "returned"): "returned",
                ("payment_status", "succeeded"): "success",
                ("shipment_status", "delivered"): "delivered",
                ("return_status", "completed"): "closed",
                ("refund_status", "succeeded"): "success",
            }
        ),
        "woocommerce": MappingProxyType(
            {
                ("order_status", "completed"): "wc-completed",
                ("payment_status", "refunded"): "wc-refunded",
                ("fulfillment_status", "returned"): "wc-returned",
                ("payment_status", "succeeded"): "completed",
                ("shipment_status", "delivered"): "completed",
                ("return_status", "completed"): "completed",
                ("refund_status", "succeeded"): "completed",
            }
        ),
        "amazon": MappingProxyType(
            {
                ("order_status", "completed"): "Closed",
                ("payment_status", "refunded"): "Refunded",
                ("fulfillment_status", "returned"): "Returned",
                ("payment_status", "succeeded"): "Captured",
                ("shipment_status", "delivered"): "Delivered",
                ("return_status", "completed"): "Closed",
                ("refund_status", "succeeded"): "Completed",
            }
        ),
        "ebay": MappingProxyType(
            {
                ("order_status", "completed"): "COMPLETED",
                ("payment_status", "refunded"): "REFUNDED",
                ("fulfillment_status", "returned"): "RETURNED",
                ("payment_status", "succeeded"): "SUCCEEDED",
                ("shipment_status", "delivered"): "DELIVERED",
                ("return_status", "completed"): "COMPLETED",
                ("refund_status", "succeeded"): "SUCCEEDED",
            }
        ),
    }
)


@dataclass(frozen=True, slots=True)
class SampleDataCheckResult:
    """Describe whether a sample directory matches the deterministic build."""

    missing_files: tuple[str, ...] = ()
    mismatched_files: tuple[str, ...] = ()
    unexpected_files: tuple[str, ...] = ()

    @property
    def is_current(self) -> bool:
        return not (self.missing_files or self.mismatched_files or self.unexpected_files)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _order_row(
    source_order_id: str,
    *,
    platform: str = "shopify",
    total: str = "100.00",
    ordered_at: str = "2026-03-01T10:00:00+00:00",
) -> dict[str, str]:
    total_decimal = Decimal(total)
    subtotal = total_decimal - Decimal("10.00")
    return {
        "order_id": f"{platform}:{source_order_id}",
        "platform": platform,
        "source_order_id": source_order_id,
        "order_number": f"DEMO-{source_order_id}",
        "ordered_at": ordered_at,
        "order_status": "fulfilled",
        "payment_status": "paid",
        "fulfillment_status": "fulfilled",
        "currency": "EUR",
        "subtotal": f"{subtotal:.2f}",
        "discount_total": "0.00",
        "shipping_total": "5.00",
        "tax_total": "5.00",
        "order_total": total,
        "customer_country": "IT",
        "cancelled_at": "",
        "cancellation_reason": "",
        "updated_at": "2026-03-02T12:00:00+00:00",
    }


def _payment_row(
    source_order_id: str,
    *,
    platform: str = "shopify",
    amount: str = "100.00",
) -> dict[str, str]:
    return {
        "payment_id": f"pay-{source_order_id}",
        "platform": platform,
        "order_id": f"{platform}:{source_order_id}",
        "source_order_id": source_order_id,
        "provider_transaction_id": f"txn-{source_order_id}",
        "payment_method": "synthetic_card",
        "payment_status": "succeeded",
        "amount": amount,
        "currency": "EUR",
        "paid_at": "2026-03-01T10:05:00+00:00",
        "created_at": "2026-03-01T10:04:00+00:00",
        "updated_at": "2026-03-01T10:05:00+00:00",
    }


def _shipment_row(
    source_order_id: str,
    *,
    platform: str = "shopify",
) -> dict[str, str]:
    return {
        "shipment_id": f"ship-{source_order_id}",
        "platform": platform,
        "order_id": f"{platform}:{source_order_id}",
        "source_order_id": source_order_id,
        "shipment_status": "delivered",
        "carrier": "synthetic_carrier",
        "shipping_service": "standard",
        "tracking_number": f"track-{source_order_id}",
        "shipped_at": "2026-03-02T09:00:00+00:00",
        "delivered_at": "2026-03-03T14:00:00+00:00",
        "warehouse_id": "synthetic-warehouse-01",
        "updated_at": "2026-03-03T14:00:00+00:00",
    }


def _return_row(
    source_order_id: str,
    *,
    platform: str = "shopify",
    amount: str = "100.00",
) -> dict[str, str]:
    return {
        "return_id": f"ret-{source_order_id}",
        "platform": platform,
        "order_id": f"{platform}:{source_order_id}",
        "source_order_id": source_order_id,
        "return_status": "completed",
        "return_reason": "synthetic_return",
        "requested_at": "2026-03-05T09:00:00+00:00",
        "received_at": "2026-03-07T09:00:00+00:00",
        "expected_refund_amount": amount,
        "currency": "EUR",
        "updated_at": "2026-03-07T09:00:00+00:00",
    }


def _refund_row(
    source_order_id: str,
    *,
    platform: str = "shopify",
    amount: str = "100.00",
) -> dict[str, str]:
    return {
        "refund_id": f"ref-{source_order_id}",
        "platform": platform,
        "order_id": f"{platform}:{source_order_id}",
        "source_order_id": source_order_id,
        "return_id": f"ret-{source_order_id}",
        "payment_id": f"pay-{source_order_id}",
        "provider_refund_id": f"provider-ref-{source_order_id}",
        "refund_status": "succeeded",
        "amount": amount,
        "currency": "EUR",
        "reason": "synthetic_refund",
        "refunded_at": "2026-03-08T09:00:00+00:00",
        "created_at": "2026-03-08T08:59:00+00:00",
        "updated_at": "2026-03-08T09:00:00+00:00",
    }


def _clean_dataset(source_order_id: str = "REC-BASE-0001") -> dict[str, list[dict[str, str]]]:
    return {
        "orders.csv": [_order_row(source_order_id)],
        "payments.csv": [_payment_row(source_order_id)],
        "shipments.csv": [_shipment_row(source_order_id)],
        "returns.csv": [],
        "refunds.csv": [],
    }


def _valid_dataset() -> dict[str, list[dict[str, str]]]:
    rows = {filename: [] for filename in CSV_SCHEMAS}
    codes = {"shopify": "SH", "woocommerce": "WC", "amazon": "AMZ", "ebay": "EB"}
    for index, platform in enumerate(PLATFORMS):
        source_order_id = f"SYN-{codes[platform]}-{1001 + index}"
        total = f"{100 + index * 10}.00"
        base = datetime(2026, 1, 1, 10, tzinfo=timezone.utc) + timedelta(days=index * 10)
        order = _order_row(source_order_id, platform=platform, total=total, ordered_at=_iso(base))
        order.update(
            order_status="completed",
            payment_status="refunded",
            fulfillment_status="returned",
            updated_at=_iso(base + timedelta(days=8)),
        )
        payment = _payment_row(source_order_id, platform=platform, amount=total)
        payment.update(
            paid_at=_iso(base + timedelta(minutes=5)),
            created_at=_iso(base + timedelta(minutes=4)),
            updated_at=_iso(base + timedelta(minutes=5)),
        )
        shipment = _shipment_row(source_order_id, platform=platform)
        shipment.update(
            shipped_at=_iso(base + timedelta(days=1)),
            delivered_at=_iso(base + timedelta(days=2)),
            updated_at=_iso(base + timedelta(days=2)),
        )
        returned = _return_row(source_order_id, platform=platform, amount=total)
        returned.update(
            requested_at=_iso(base + timedelta(days=4)),
            received_at=_iso(base + timedelta(days=6)),
            updated_at=_iso(base + timedelta(days=6)),
        )
        refund = _refund_row(source_order_id, platform=platform, amount=total)
        refund.update(
            refunded_at=_iso(base + timedelta(days=7)),
            created_at=_iso(base + timedelta(days=7, minutes=-1)),
            updated_at=_iso(base + timedelta(days=7)),
        )
        rows["orders.csv"].append(order)
        rows["payments.csv"].append(payment)
        rows["shipments.csv"].append(shipment)
        rows["returns.csv"].append(returned)
        rows["refunds.csv"].append(refund)
    return rows


def _scenario_dataset(code: str) -> dict[str, list[dict[str, str]]]:
    source_order_id = f"{code}-0001"
    rows = _clean_dataset(source_order_id)
    order = rows["orders.csv"][0]
    payment = rows["payments.csv"][0]
    shipment = rows["shipments.csv"][0]

    if code == "REC-01":
        payment["amount"] = "90.00"
        order["fulfillment_status"] = "unfulfilled"
        shipment.update(shipment_status="pending", tracking_number="", shipped_at="", delivered_at="")
    elif code == "REC-02":
        order["fulfillment_status"] = "unfulfilled"
        shipment.update(shipment_status="pending", tracking_number="", shipped_at="", delivered_at="")
    elif code == "REC-03":
        order["payment_status"] = "pending"
        payment.update(payment_status="failed", paid_at="")
        shipment.update(shipment_status="shipped", delivered_at="")
    elif code == "REC-04":
        order.update(subtotal="190.00", order_total="200.00")
        payment["amount"] = "100.00"
        rows["payments.csv"].append(dict(payment))
    elif code == "REC-05":
        shipment.update(shipment_status="shipped", tracking_number="", delivered_at="")
    elif code == "REC-06":
        order.update(
            order_status="cancelled",
            cancelled_at="2026-03-01T11:00:00+00:00",
            cancellation_reason="synthetic_cancellation",
        )
        shipment.update(shipment_status="shipped", delivered_at="")
    elif code == "REC-07":
        order["fulfillment_status"] = "returned"
        returned = _return_row(source_order_id)
        returned.update(return_status="received", received_at="2026-03-07T09:00:00+00:00")
        rows["returns.csv"].append(returned)
    elif code == "REC-08":
        order["payment_status"] = "partially_refunded"
        refund = _refund_row(source_order_id, amount="120.00")
        refund["return_id"] = ""
        rows["refunds.csv"].append(refund)
    elif code == "REC-09":
        order["payment_status"] = "refunded"
        refund = _refund_row(source_order_id, amount="50.00")
        refund["return_id"] = ""
        rows["refunds.csv"].extend((refund, dict(refund)))
    elif code == "REC-10":
        missing_source = "REC10-MISSING-9001"
        orphan = _shipment_row(missing_source)
        orphan.update(shipment_status="pending", tracking_number="", shipped_at="", delivered_at="")
        rows["shipments.csv"].append(orphan)
    else:
        raise ValueError(f"Unsupported scenario code: {code}")

    return rows


def _source_column_name(platform: str, canonical_name: str) -> str:
    return f"{SOURCE_PREFIXES[platform]}_{_SOURCE_ALIASES[canonical_name]}"


def _source_value(platform: str, filename: str, column_name: str, value: str) -> str:
    if not value:
        return value
    status_value = _SOURCE_STATUS_VALUES[platform].get((column_name, value))
    if status_value is not None:
        return status_value
    column = CSV_SCHEMAS[filename].get_column(column_name)
    if column.data_type is DataType.DATETIME:
        if platform == "woocommerce":
            return value.replace("+00:00", "Z")
        if platform == "amazon":
            return value.replace("T", " ")
        if platform == "ebay":
            return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S%z")
    if column.data_type is DataType.DECIMAL:
        if platform == "woocommerce":
            return value.replace(".", ",")
        if platform == "ebay":
            return str(int(Decimal(value) * 100))
    return value


def _source_export(
    platform: str,
    filename: str,
    canonical_rows: list[dict[str, str]],
) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    canonical_columns = tuple(
        column.name
        for column in CSV_SCHEMAS[filename].columns
        if column.name not in {"platform", "order_id"}
    )
    source_columns = tuple(
        _source_column_name(platform, column) for column in canonical_columns
    )
    source_rows = [
        {
            _source_column_name(platform, column): _source_value(
                platform, filename, column, row.get(column, "")
            )
            for column in canonical_columns
        }
        for row in canonical_rows
    ]
    return source_columns, source_rows


def _csv_bytes(
    filename: str,
    rows: list[dict[str, str]],
    *,
    columns: tuple[str, ...] | None = None,
) -> bytes:
    fieldnames = columns or CSV_SCHEMAS[filename].column_names
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in fieldnames})
    return output.getvalue().encode("utf-8")


def _add_dataset(
    files: dict[str, bytes],
    directory: str,
    rows: Mapping[str, list[dict[str, str]]],
    *,
    columns_by_file: Mapping[str, tuple[str, ...]] | None = None,
) -> None:
    for filename in CSV_SCHEMAS:
        columns = columns_by_file.get(filename) if columns_by_file else None
        files[f"{directory}/{filename}"] = _csv_bytes(
            filename, rows[filename], columns=columns
        )


def _manifest() -> dict[str, object]:
    scenarios = (
        ("REC-01", "PAYMENT_AMOUNT_MISMATCH", "payment-amount-mismatch", "2026-03-01T11:00:00+00:00"),
        ("REC-02", "PAID_NOT_SHIPPED_ON_TIME", "paid-not-shipped-on-time", "2026-03-04T12:00:00+00:00"),
        ("REC-03", "SHIPPED_WITHOUT_CONFIRMED_PAYMENT", "shipped-without-confirmed-payment", "2026-03-02T12:00:00+00:00"),
        ("REC-04", "DUPLICATE_PAYMENT", "duplicate-payment", None),
        ("REC-05", "SHIPMENT_WITHOUT_TRACKING", "shipment-without-tracking", None),
        ("REC-06", "CANCELLED_ORDER_SHIPPED", "cancelled-order-shipped", None),
        ("REC-07", "RETURN_RECEIVED_NOT_REFUNDED", "return-received-not-refunded", "2026-03-15T10:00:00+00:00"),
        ("REC-08", "REFUND_EXCEEDS_PAYMENT", "refund-exceeds-payment", None),
        ("REC-09", "DUPLICATE_REFUND", "duplicate-refund", None),
        ("REC-10", "CROSS_SYSTEM_RECORD_MISSING", "cross-system-record-missing", None),
    )
    scenario_entries = []
    for code, anomaly_code, slug, reference_at in scenarios:
        affected = "shopify:REC10-MISSING-9001" if code == "REC-10" else f"shopify:{code}-0001"
        scenario_entries.append(
            {
                "code": code,
                "anomaly_code": anomaly_code,
                "directory": f"scenarios/{code.lower()}-{slug}",
                "description": f"Synthetic isolated scenario for {anomaly_code}.",
                "reference_at": reference_at,
                "affected_order_ids": [affected],
                "expected_anomaly_count": 1,
                "expected_validation": {
                    "reconciliation_ready": True,
                    "blocking_message_count": 0,
                    "relationship_finding_count": 1 if code == "REC-10" else 0,
                },
            }
        )
    return {
        "format_version": 1,
        "synthetic_only": True,
        "canonical_valid_dataset": {
            "directory": "normalized/valid",
            "platforms": list(PLATFORMS),
            "currency": "EUR",
            "expected_validation": {
                "reconciliation_ready": True,
                "blocking_message_count": 0,
                "relationship_finding_count": 0,
            },
        },
        "scenarios": scenario_entries,
        "invalid_examples": [
            {
                "directory": "invalid/missing-required-column",
                "description": "orders.csv omits the required currency column.",
                "expected_stage": "read",
                "expected_code": "missing_required_columns",
            },
            {
                "directory": "invalid/invalid-datetime",
                "description": "orders.csv contains an impossible ordered_at value.",
                "expected_stage": "value",
                "expected_code": "invalid_datetime",
            },
            {
                "directory": "invalid/missing-paid-at",
                "description": "A succeeded payment omits paid_at.",
                "expected_stage": "integrity",
                "expected_code": "missing_paid_at",
            },
            {
                "directory": "invalid/duplicate-order-id",
                "description": "orders.csv repeats a blocking order identifier.",
                "expected_stage": "uniqueness",
                "expected_code": "duplicate_order_id",
            },
        ],
        "source_exports": {
            "directory": "sources",
            "platforms": list(PLATFORMS),
            "disclaimer": "Documented portfolio simulations, not official API contracts.",
        },
    }


def _sample_readme() -> str:
    return r"""# Synthetic sample data

Every identifier, amount, timestamp, and descriptive value in this directory is deterministic and invented for this public portfolio project. The four platform names identify the simulated source being demonstrated; the files are not official API or export contracts.

## Structure

- `normalized/valid/`: canonical five-file dataset covering Shopify, WooCommerce, Amazon, and eBay without blocking errors or relationship findings.
- `scenarios/`: ten isolated five-file datasets, one for each future `REC-01`–`REC-10` rule.
- `invalid/`: separate five-file datasets that intentionally fail read, value, integrity, or uniqueness validation.
- `sources/<platform>/`: simulated source exports used by the normalization examples.
- `manifest.json`: machine-readable expected validation and future anomaly outcomes.

All monetary values are EUR. Canonical timestamps use timezone-aware ISO 8601 strings and canonical order identifiers use `platform:source_order_id`.

## Verification

From the project root, check that the committed files match the deterministic generator without writing anything:

```powershell
.\.venv\Scripts\python.exe -m kz_ecomops.sample_data data/sample --check
```

The scenario manifest describes future reconciliation expectations only. The `REC-01`–`REC-10` engine is not implemented yet.
"""


def build_sample_files() -> Mapping[str, bytes]:
    """Build every managed sample file entirely in memory."""

    files: dict[str, bytes] = {}
    valid_rows = _valid_dataset()
    _add_dataset(files, "normalized/valid", valid_rows)

    manifest = _manifest()
    for scenario in manifest["scenarios"]:  # type: ignore[index]
        code = scenario["code"]  # type: ignore[index]
        _add_dataset(files, scenario["directory"], _scenario_dataset(code))  # type: ignore[arg-type,index]

    missing_column_rows = _clean_dataset("INVALID-COLUMN-0001")
    order_columns = tuple(
        column for column in CSV_SCHEMAS["orders.csv"].column_names if column != "currency"
    )
    _add_dataset(
        files,
        "invalid/missing-required-column",
        missing_column_rows,
        columns_by_file={"orders.csv": order_columns},
    )

    invalid_date_rows = _clean_dataset("INVALID-DATE-0001")
    invalid_date_rows["orders.csv"][0]["ordered_at"] = "2026-99-40T10:00:00+00:00"
    _add_dataset(files, "invalid/invalid-datetime", invalid_date_rows)

    integrity_rows = _clean_dataset("INVALID-INTEGRITY-0001")
    integrity_rows["payments.csv"][0]["paid_at"] = ""
    _add_dataset(files, "invalid/missing-paid-at", integrity_rows)

    duplicate_rows = _clean_dataset("INVALID-DUPLICATE-0001")
    duplicate_rows["orders.csv"].append(dict(duplicate_rows["orders.csv"][0]))
    _add_dataset(files, "invalid/duplicate-order-id", duplicate_rows)

    for platform in PLATFORMS:
        for filename in CSV_SCHEMAS:
            platform_rows = [
                row for row in valid_rows[filename] if row["platform"] == platform
            ]
            columns, source_rows = _source_export(platform, filename, platform_rows)
            files[f"sources/{platform}/{filename}"] = _csv_bytes(
                filename, source_rows, columns=columns
            )

    files["README.md"] = _sample_readme().encode("utf-8")
    files["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    return MappingProxyType(dict(sorted(files.items())))


def _managed_contents_match(
    relative_path: str,
    actual_content: bytes,
    expected_content: bytes,
) -> bool:
    """Compare managed content, allowing only LF/CRLF text representation changes."""

    if Path(relative_path).suffix.casefold() in _MANAGED_TEXT_SUFFIXES:
        return actual_content.replace(b"\r\n", b"\n") == expected_content.replace(
            b"\r\n", b"\n"
        )
    return actual_content == expected_content


def check_sample_data(destination: str | Path) -> SampleDataCheckResult:
    """Compare managed files without writing, accepting platform text newlines."""

    root = Path(destination)
    expected = build_sample_files()
    existing = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
    } if root.exists() else {}
    missing = tuple(path for path in expected if path not in existing)
    mismatched = tuple(
        path
        for path, source in existing.items()
        if path in expected
        and not _managed_contents_match(path, source.read_bytes(), expected[path])
    )
    unexpected = tuple(sorted(set(existing) - set(expected)))
    return SampleDataCheckResult(
        missing_files=missing,
        mismatched_files=tuple(sorted(mismatched)),
        unexpected_files=unexpected,
    )


def generate_sample_data(destination: str | Path) -> SampleDataCheckResult:
    """Create missing managed files without overwriting or deleting existing files."""

    root = Path(destination)
    check = check_sample_data(root)
    if check.unexpected_files:
        raise FileExistsError(
            "Destination contains unmanaged files; generation was not started."
        )
    if check.mismatched_files:
        raise FileExistsError(
            "Destination contains modified managed files; generation will not overwrite them."
        )
    expected = build_sample_files()
    for relative_path in check.missing_files:
        target = root / Path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(expected[relative_path])
    return check_sample_data(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare files without writing or overwriting anything",
    )
    args = parser.parse_args(argv)
    result = check_sample_data(args.destination) if args.check else generate_sample_data(args.destination)
    if result.is_current:
        print("Synthetic sample data is current.")
        return 0
    print(
        f"Sample data differs: {len(result.missing_files)} missing, "
        f"{len(result.mismatched_files)} mismatched, "
        f"{len(result.unexpected_files)} unexpected."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
