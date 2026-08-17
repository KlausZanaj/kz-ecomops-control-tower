"""Immutable schema definitions for the required MVP CSV files."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class DataType(StrEnum):
    """Logical data types used by the required MVP CSV schemas."""

    STRING = "string"
    DECIMAL = "decimal"
    DATETIME = "datetime"


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    """Describe one column without validating its values."""

    name: str
    data_type: DataType
    required: bool
    allowed_values: frozenset[str] | None = None
    minimum: Decimal | None = None
    minimum_inclusive: bool = True
    decimal_places: int | None = None


@dataclass(frozen=True, slots=True)
class CsvSchema:
    """Describe the ordered columns of one normalized CSV file."""

    filename: str
    columns: tuple[ColumnSchema, ...]

    @property
    def column_names(self) -> tuple[str, ...]:
        """Return column names in their documented order."""

        return tuple(column.name for column in self.columns)

    @property
    def required_columns(self) -> tuple[ColumnSchema, ...]:
        """Return columns that must be present in the CSV file."""

        return tuple(column for column in self.columns if column.required)

    def get_column(self, name: str) -> ColumnSchema:
        """Return a column schema or raise a descriptive error."""

        for column in self.columns:
            if column.name == name:
                return column
        raise KeyError(f"Column {name!r} is not defined in schema {self.filename!r}.")


SUPPORTED_PLATFORMS = frozenset({"shopify", "woocommerce", "amazon", "ebay"})
SUPPORTED_CURRENCIES = frozenset({"EUR"})

ORDER_STATUSES = frozenset(
    {"pending", "confirmed", "fulfilled", "completed", "cancelled"}
)
ORDER_PAYMENT_STATUSES = frozenset(
    {"pending", "partially_paid", "paid", "failed", "partially_refunded", "refunded"}
)
FULFILLMENT_STATUSES = frozenset(
    {"unfulfilled", "partially_fulfilled", "fulfilled", "returned", "cancelled"}
)
PAYMENT_TRANSACTION_STATUSES = frozenset(
    {"pending", "succeeded", "failed", "cancelled", "reversed"}
)
SHIPMENT_STATUSES = frozenset(
    {"pending", "ready", "shipped", "delivered", "failed", "cancelled", "returned"}
)
RETURN_STATUSES = frozenset(
    {"requested", "approved", "in_transit", "received", "completed", "rejected", "cancelled"}
)
REFUND_STATUSES = frozenset({"pending", "succeeded", "failed", "cancelled"})

_ZERO = Decimal("0")

_ORDERS_SCHEMA = CsvSchema(
    filename="orders.csv",
    columns=(
        ColumnSchema("order_id", DataType.STRING, True),
        ColumnSchema("platform", DataType.STRING, True, SUPPORTED_PLATFORMS),
        ColumnSchema("source_order_id", DataType.STRING, True),
        ColumnSchema("order_number", DataType.STRING, False),
        ColumnSchema("ordered_at", DataType.DATETIME, True),
        ColumnSchema("order_status", DataType.STRING, True, ORDER_STATUSES),
        ColumnSchema(
            "payment_status", DataType.STRING, True, ORDER_PAYMENT_STATUSES
        ),
        ColumnSchema(
            "fulfillment_status", DataType.STRING, True, FULFILLMENT_STATUSES
        ),
        ColumnSchema("currency", DataType.STRING, True, SUPPORTED_CURRENCIES),
        ColumnSchema(
            "subtotal", DataType.DECIMAL, True, minimum=_ZERO, decimal_places=2
        ),
        ColumnSchema(
            "discount_total", DataType.DECIMAL, True, minimum=_ZERO, decimal_places=2
        ),
        ColumnSchema(
            "shipping_total", DataType.DECIMAL, True, minimum=_ZERO, decimal_places=2
        ),
        ColumnSchema(
            "tax_total", DataType.DECIMAL, True, minimum=_ZERO, decimal_places=2
        ),
        ColumnSchema(
            "order_total", DataType.DECIMAL, True, minimum=_ZERO, decimal_places=2
        ),
        ColumnSchema("customer_country", DataType.STRING, False),
        ColumnSchema("cancelled_at", DataType.DATETIME, False),
        ColumnSchema("cancellation_reason", DataType.STRING, False),
        ColumnSchema("updated_at", DataType.DATETIME, True),
    ),
)

_PAYMENTS_SCHEMA = CsvSchema(
    filename="payments.csv",
    columns=(
        ColumnSchema("payment_id", DataType.STRING, True),
        ColumnSchema("platform", DataType.STRING, True, SUPPORTED_PLATFORMS),
        ColumnSchema("order_id", DataType.STRING, True),
        ColumnSchema("source_order_id", DataType.STRING, True),
        ColumnSchema("provider_transaction_id", DataType.STRING, False),
        ColumnSchema("payment_method", DataType.STRING, False),
        ColumnSchema(
            "payment_status", DataType.STRING, True, PAYMENT_TRANSACTION_STATUSES
        ),
        ColumnSchema(
            "amount",
            DataType.DECIMAL,
            True,
            minimum=_ZERO,
            minimum_inclusive=False,
            decimal_places=2,
        ),
        ColumnSchema("currency", DataType.STRING, True, SUPPORTED_CURRENCIES),
        ColumnSchema("paid_at", DataType.DATETIME, False),
        ColumnSchema("created_at", DataType.DATETIME, True),
        ColumnSchema("updated_at", DataType.DATETIME, True),
    ),
)

_SHIPMENTS_SCHEMA = CsvSchema(
    filename="shipments.csv",
    columns=(
        ColumnSchema("shipment_id", DataType.STRING, True),
        ColumnSchema("platform", DataType.STRING, True, SUPPORTED_PLATFORMS),
        ColumnSchema("order_id", DataType.STRING, True),
        ColumnSchema("source_order_id", DataType.STRING, True),
        ColumnSchema("shipment_status", DataType.STRING, True, SHIPMENT_STATUSES),
        ColumnSchema("carrier", DataType.STRING, False),
        ColumnSchema("shipping_service", DataType.STRING, False),
        ColumnSchema("tracking_number", DataType.STRING, False),
        ColumnSchema("shipped_at", DataType.DATETIME, False),
        ColumnSchema("delivered_at", DataType.DATETIME, False),
        ColumnSchema("warehouse_id", DataType.STRING, False),
        ColumnSchema("updated_at", DataType.DATETIME, True),
    ),
)

_RETURNS_SCHEMA = CsvSchema(
    filename="returns.csv",
    columns=(
        ColumnSchema("return_id", DataType.STRING, True),
        ColumnSchema("platform", DataType.STRING, True, SUPPORTED_PLATFORMS),
        ColumnSchema("order_id", DataType.STRING, True),
        ColumnSchema("source_order_id", DataType.STRING, True),
        ColumnSchema("return_status", DataType.STRING, True, RETURN_STATUSES),
        ColumnSchema("return_reason", DataType.STRING, False),
        ColumnSchema("requested_at", DataType.DATETIME, True),
        ColumnSchema("received_at", DataType.DATETIME, False),
        ColumnSchema(
            "expected_refund_amount", DataType.DECIMAL, False, decimal_places=2
        ),
        ColumnSchema("currency", DataType.STRING, False, SUPPORTED_CURRENCIES),
        ColumnSchema("updated_at", DataType.DATETIME, True),
    ),
)

_REFUNDS_SCHEMA = CsvSchema(
    filename="refunds.csv",
    columns=(
        ColumnSchema("refund_id", DataType.STRING, True),
        ColumnSchema("platform", DataType.STRING, True, SUPPORTED_PLATFORMS),
        ColumnSchema("order_id", DataType.STRING, True),
        ColumnSchema("source_order_id", DataType.STRING, True),
        ColumnSchema("return_id", DataType.STRING, False),
        ColumnSchema("payment_id", DataType.STRING, False),
        ColumnSchema("provider_refund_id", DataType.STRING, False),
        ColumnSchema("refund_status", DataType.STRING, True, REFUND_STATUSES),
        ColumnSchema(
            "amount",
            DataType.DECIMAL,
            True,
            minimum=_ZERO,
            minimum_inclusive=False,
            decimal_places=2,
        ),
        ColumnSchema("currency", DataType.STRING, True, SUPPORTED_CURRENCIES),
        ColumnSchema("reason", DataType.STRING, False),
        ColumnSchema("refunded_at", DataType.DATETIME, False),
        ColumnSchema("created_at", DataType.DATETIME, True),
        ColumnSchema("updated_at", DataType.DATETIME, True),
    ),
)

CSV_SCHEMAS: Mapping[str, CsvSchema] = MappingProxyType(
    {
        schema.filename: schema
        for schema in (
            _ORDERS_SCHEMA,
            _PAYMENTS_SCHEMA,
            _SHIPMENTS_SCHEMA,
            _RETURNS_SCHEMA,
            _REFUNDS_SCHEMA,
        )
    }
)
