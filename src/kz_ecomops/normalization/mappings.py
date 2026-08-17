"""Immutable mappings for documented synthetic platform export formats."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from kz_ecomops.validation import CSV_SCHEMAS


class SourceAmountStyle(StrEnum):
    """Supported amount encodings in the simulated source exports."""

    POINT_DECIMAL = "point_decimal"
    COMMA_DECIMAL = "comma_decimal"
    INTEGER_CENTS = "integer_cents"


class SourceDateStyle(StrEnum):
    """Supported date encodings in the simulated source exports."""

    ISO_OFFSET = "iso_offset"
    ISO_ZULU = "iso_zulu"
    SPACE_OFFSET = "space_offset"
    COMPACT_OFFSET = "compact_offset"


@dataclass(frozen=True, slots=True)
class PlatformMapping:
    """Describe one simulated source format without claiming an official contract."""

    platform: str
    column_mappings: Mapping[str, Mapping[str, str]]
    status_mappings: Mapping[str, Mapping[str, Mapping[str, str]]]
    identifier_columns: Mapping[str, tuple[str, ...]]
    date_style: SourceDateStyle
    amount_style: SourceAmountStyle

    def __post_init__(self) -> None:
        frozen_columns = MappingProxyType(
            {
                filename: MappingProxyType(dict(columns))
                for filename, columns in self.column_mappings.items()
            }
        )
        frozen_statuses = MappingProxyType(
            {
                filename: MappingProxyType(
                    {
                        column: MappingProxyType(dict(values))
                        for column, values in columns.items()
                    }
                )
                for filename, columns in self.status_mappings.items()
            }
        )
        frozen_identifiers = MappingProxyType(dict(self.identifier_columns))
        object.__setattr__(self, "column_mappings", frozen_columns)
        object.__setattr__(self, "status_mappings", frozen_statuses)
        object.__setattr__(self, "identifier_columns", frozen_identifiers)


_SOURCE_ALIASES = {
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

_IDENTIFIER_COLUMNS = {
    "orders.csv": ("source_order_id",),
    "payments.csv": (
        "payment_id",
        "source_order_id",
        "provider_transaction_id",
    ),
    "shipments.csv": ("shipment_id", "source_order_id", "tracking_number"),
    "returns.csv": ("return_id", "source_order_id"),
    "refunds.csv": (
        "refund_id",
        "source_order_id",
        "return_id",
        "payment_id",
        "provider_refund_id",
    ),
}


def _column_mappings(prefix: str) -> dict[str, dict[str, str]]:
    return {
        filename: {
            column.name: f"{prefix}_{_SOURCE_ALIASES[column.name]}"
            for column in schema.columns
            if column.name not in {"platform", "order_id"}
        }
        for filename, schema in CSV_SCHEMAS.items()
    }


def _raw_status(platform: str, filename: str, column: str, canonical: str) -> str:
    if platform == "shopify":
        if filename == "orders.csv" and column == "order_status" and canonical == "completed":
            return "closed"
        if filename == "payments.csv" and canonical == "succeeded":
            return "success"
        if filename == "returns.csv" and canonical == "completed":
            return "closed"
        if filename == "refunds.csv" and canonical == "succeeded":
            return "success"
        return canonical
    if platform == "woocommerce":
        if filename == "orders.csv":
            return f"wc-{canonical.replace('_', '-')}"
        if filename in {"payments.csv", "refunds.csv"} and canonical == "succeeded":
            return "completed"
        if filename in {"shipments.csv", "returns.csv"} and canonical in {"delivered", "completed"}:
            return "completed"
        return canonical.replace("_", "-")
    if platform == "amazon":
        special = {
            ("orders.csv", "order_status", "completed"): "Closed",
            ("payments.csv", "payment_status", "succeeded"): "Captured",
            ("returns.csv", "return_status", "completed"): "Closed",
            ("refunds.csv", "refund_status", "succeeded"): "Completed",
        }
        return special.get(
            (filename, column, canonical),
            "".join(part.capitalize() for part in canonical.split("_")),
        )
    return canonical.upper()


def _status_mappings(platform: str) -> dict[str, dict[str, dict[str, str]]]:
    mappings: dict[str, dict[str, dict[str, str]]] = {}
    for filename, schema in CSV_SCHEMAS.items():
        file_mappings: dict[str, dict[str, str]] = {}
        for column in schema.columns:
            if column.allowed_values is None or "status" not in column.name:
                continue
            file_mappings[column.name] = {
                _raw_status(platform, filename, column.name, canonical): canonical
                for canonical in sorted(column.allowed_values)
            }
        mappings[filename] = file_mappings
    return mappings


def _mapping(
    platform: str,
    prefix: str,
    date_style: SourceDateStyle,
    amount_style: SourceAmountStyle,
) -> PlatformMapping:
    return PlatformMapping(
        platform=platform,
        column_mappings=_column_mappings(prefix),
        status_mappings=_status_mappings(platform),
        identifier_columns=_IDENTIFIER_COLUMNS,
        date_style=date_style,
        amount_style=amount_style,
    )


PLATFORM_MAPPINGS: Mapping[str, PlatformMapping] = MappingProxyType(
    {
        "shopify": _mapping(
            "shopify",
            "sh",
            SourceDateStyle.ISO_OFFSET,
            SourceAmountStyle.POINT_DECIMAL,
        ),
        "woocommerce": _mapping(
            "woocommerce",
            "wc",
            SourceDateStyle.ISO_ZULU,
            SourceAmountStyle.COMMA_DECIMAL,
        ),
        "amazon": _mapping(
            "amazon",
            "amz",
            SourceDateStyle.SPACE_OFFSET,
            SourceAmountStyle.POINT_DECIMAL,
        ),
        "ebay": _mapping(
            "ebay",
            "eb",
            SourceDateStyle.COMPACT_OFFSET,
            SourceAmountStyle.INTEGER_CENTS,
        ),
    }
)

SUPPORTED_SOURCE_PLATFORMS = frozenset(PLATFORM_MAPPINGS)
