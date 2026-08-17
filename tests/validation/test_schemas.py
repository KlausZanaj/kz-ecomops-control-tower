"""Tests for the immutable MVP CSV schema definitions."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from types import MappingProxyType

import pytest

from kz_ecomops.validation import (
    CSV_SCHEMAS,
    FULFILLMENT_STATUSES,
    ORDER_PAYMENT_STATUSES,
    ORDER_STATUSES,
    PAYMENT_TRANSACTION_STATUSES,
    REFUND_STATUSES,
    RETURN_STATUSES,
    SHIPMENT_STATUSES,
    SUPPORTED_CURRENCIES,
    SUPPORTED_PLATFORMS,
    ColumnSchema,
    CsvSchema,
    DataType,
)


REQUIRED_FILENAMES = {
    "orders.csv",
    "payments.csv",
    "shipments.csv",
    "returns.csv",
    "refunds.csv",
}

OPTIONAL_FILENAMES = {
    "order_items.csv",
    "products.csv",
    "inventory.csv",
    "ad_spend.csv",
    "traffic.csv",
}

COLUMN_COUNTS = {
    "orders.csv": 18,
    "payments.csv": 12,
    "shipments.csv": 12,
    "returns.csv": 11,
    "refunds.csv": 14,
}

REQUIRED_COLUMNS = {
    "orders.csv": {
        "order_id",
        "platform",
        "source_order_id",
        "ordered_at",
        "order_status",
        "payment_status",
        "fulfillment_status",
        "currency",
        "subtotal",
        "discount_total",
        "shipping_total",
        "tax_total",
        "order_total",
        "updated_at",
    },
    "payments.csv": {
        "payment_id",
        "platform",
        "order_id",
        "source_order_id",
        "payment_status",
        "amount",
        "currency",
        "created_at",
        "updated_at",
    },
    "shipments.csv": {
        "shipment_id",
        "platform",
        "order_id",
        "source_order_id",
        "shipment_status",
        "updated_at",
    },
    "returns.csv": {
        "return_id",
        "platform",
        "order_id",
        "source_order_id",
        "return_status",
        "requested_at",
        "updated_at",
    },
    "refunds.csv": {
        "refund_id",
        "platform",
        "order_id",
        "source_order_id",
        "refund_status",
        "amount",
        "currency",
        "created_at",
        "updated_at",
    },
}

COLUMN_TYPES = {
    "orders.csv": {
        "order_id": DataType.STRING,
        "platform": DataType.STRING,
        "source_order_id": DataType.STRING,
        "order_number": DataType.STRING,
        "ordered_at": DataType.DATETIME,
        "order_status": DataType.STRING,
        "payment_status": DataType.STRING,
        "fulfillment_status": DataType.STRING,
        "currency": DataType.STRING,
        "subtotal": DataType.DECIMAL,
        "discount_total": DataType.DECIMAL,
        "shipping_total": DataType.DECIMAL,
        "tax_total": DataType.DECIMAL,
        "order_total": DataType.DECIMAL,
        "customer_country": DataType.STRING,
        "cancelled_at": DataType.DATETIME,
        "cancellation_reason": DataType.STRING,
        "updated_at": DataType.DATETIME,
    },
    "payments.csv": {
        "payment_id": DataType.STRING,
        "platform": DataType.STRING,
        "order_id": DataType.STRING,
        "source_order_id": DataType.STRING,
        "provider_transaction_id": DataType.STRING,
        "payment_method": DataType.STRING,
        "payment_status": DataType.STRING,
        "amount": DataType.DECIMAL,
        "currency": DataType.STRING,
        "paid_at": DataType.DATETIME,
        "created_at": DataType.DATETIME,
        "updated_at": DataType.DATETIME,
    },
    "shipments.csv": {
        "shipment_id": DataType.STRING,
        "platform": DataType.STRING,
        "order_id": DataType.STRING,
        "source_order_id": DataType.STRING,
        "shipment_status": DataType.STRING,
        "carrier": DataType.STRING,
        "shipping_service": DataType.STRING,
        "tracking_number": DataType.STRING,
        "shipped_at": DataType.DATETIME,
        "delivered_at": DataType.DATETIME,
        "warehouse_id": DataType.STRING,
        "updated_at": DataType.DATETIME,
    },
    "returns.csv": {
        "return_id": DataType.STRING,
        "platform": DataType.STRING,
        "order_id": DataType.STRING,
        "source_order_id": DataType.STRING,
        "return_status": DataType.STRING,
        "return_reason": DataType.STRING,
        "requested_at": DataType.DATETIME,
        "received_at": DataType.DATETIME,
        "expected_refund_amount": DataType.DECIMAL,
        "currency": DataType.STRING,
        "updated_at": DataType.DATETIME,
    },
    "refunds.csv": {
        "refund_id": DataType.STRING,
        "platform": DataType.STRING,
        "order_id": DataType.STRING,
        "source_order_id": DataType.STRING,
        "return_id": DataType.STRING,
        "payment_id": DataType.STRING,
        "provider_refund_id": DataType.STRING,
        "refund_status": DataType.STRING,
        "amount": DataType.DECIMAL,
        "currency": DataType.STRING,
        "reason": DataType.STRING,
        "refunded_at": DataType.DATETIME,
        "created_at": DataType.DATETIME,
        "updated_at": DataType.DATETIME,
    },
}


def test_registry_contains_exactly_required_csv_files() -> None:
    assert set(CSV_SCHEMAS) == REQUIRED_FILENAMES


@pytest.mark.parametrize("filename", sorted(OPTIONAL_FILENAMES))
def test_optional_csv_file_is_not_registered(filename: str) -> None:
    assert filename not in CSV_SCHEMAS


@pytest.mark.parametrize("filename, expected", COLUMN_COUNTS.items())
def test_schema_has_documented_column_count(filename: str, expected: int) -> None:
    assert len(CSV_SCHEMAS[filename].columns) == expected


@pytest.mark.parametrize("filename, expected", REQUIRED_COLUMNS.items())
def test_schema_has_exact_required_columns(filename: str, expected: set[str]) -> None:
    actual = {column.name for column in CSV_SCHEMAS[filename].required_columns}
    assert actual == expected


@pytest.mark.parametrize("filename", sorted(REQUIRED_FILENAMES))
def test_schema_has_no_duplicate_columns(filename: str) -> None:
    names = CSV_SCHEMAS[filename].column_names
    assert len(names) == len(set(names))


@pytest.mark.parametrize("filename, expected", COLUMN_TYPES.items())
def test_schema_has_documented_logical_types(
    filename: str, expected: dict[str, DataType]
) -> None:
    actual = {column.name: column.data_type for column in CSV_SCHEMAS[filename].columns}
    assert actual == expected


def test_data_type_has_only_required_text_values() -> None:
    assert {data_type.value for data_type in DataType} == {
        "string",
        "decimal",
        "datetime",
    }


def test_supported_platforms_are_exact_and_used_by_every_schema() -> None:
    assert SUPPORTED_PLATFORMS == frozenset(
        {"shopify", "woocommerce", "amazon", "ebay"}
    )
    for schema in CSV_SCHEMAS.values():
        assert schema.get_column("platform").allowed_values == SUPPORTED_PLATFORMS


def test_eur_is_the_only_supported_currency() -> None:
    assert SUPPORTED_CURRENCIES == frozenset({"EUR"})
    for filename in ("orders.csv", "payments.csv", "returns.csv", "refunds.csv"):
        assert CSV_SCHEMAS[filename].get_column("currency").allowed_values == frozenset(
            {"EUR"}
        )


def test_allowed_status_sets_are_exact_and_assigned() -> None:
    expected = {
        ORDER_STATUSES: {"pending", "confirmed", "fulfilled", "completed", "cancelled"},
        ORDER_PAYMENT_STATUSES: {
            "pending",
            "partially_paid",
            "paid",
            "failed",
            "partially_refunded",
            "refunded",
        },
        FULFILLMENT_STATUSES: {
            "unfulfilled",
            "partially_fulfilled",
            "fulfilled",
            "returned",
            "cancelled",
        },
        PAYMENT_TRANSACTION_STATUSES: {
            "pending",
            "succeeded",
            "failed",
            "cancelled",
            "reversed",
        },
        SHIPMENT_STATUSES: {
            "pending",
            "ready",
            "shipped",
            "delivered",
            "failed",
            "cancelled",
            "returned",
        },
        RETURN_STATUSES: {
            "requested",
            "approved",
            "in_transit",
            "received",
            "completed",
            "rejected",
            "cancelled",
        },
        REFUND_STATUSES: {"pending", "succeeded", "failed", "cancelled"},
    }
    for actual, documented in expected.items():
        assert actual == frozenset(documented)

    assignments = {
        ("orders.csv", "order_status"): ORDER_STATUSES,
        ("orders.csv", "payment_status"): ORDER_PAYMENT_STATUSES,
        ("orders.csv", "fulfillment_status"): FULFILLMENT_STATUSES,
        ("payments.csv", "payment_status"): PAYMENT_TRANSACTION_STATUSES,
        ("shipments.csv", "shipment_status"): SHIPMENT_STATUSES,
        ("returns.csv", "return_status"): RETURN_STATUSES,
        ("refunds.csv", "refund_status"): REFUND_STATUSES,
    }
    for (filename, column_name), allowed_values in assignments.items():
        assert CSV_SCHEMAS[filename].get_column(column_name).allowed_values == allowed_values


@pytest.mark.parametrize(
    "filename, column_name, minimum_inclusive",
    [
        ("orders.csv", "subtotal", True),
        ("orders.csv", "discount_total", True),
        ("orders.csv", "shipping_total", True),
        ("orders.csv", "tax_total", True),
        ("orders.csv", "order_total", True),
        ("payments.csv", "amount", False),
        ("refunds.csv", "amount", False),
    ],
)
def test_documented_monetary_minimums(
    filename: str, column_name: str, minimum_inclusive: bool
) -> None:
    column = CSV_SCHEMAS[filename].get_column(column_name)
    assert column.minimum == Decimal("0")
    assert column.minimum_inclusive is minimum_inclusive


def test_undocumented_return_amount_minimum_is_not_invented() -> None:
    column = CSV_SCHEMAS["returns.csv"].get_column("expected_refund_amount")
    assert column.minimum is None


def test_column_schema_is_frozen_and_slotted() -> None:
    column = CSV_SCHEMAS["orders.csv"].get_column("order_id")
    with pytest.raises(FrozenInstanceError):
        column.required = False  # type: ignore[misc]
    assert not hasattr(column, "__dict__")


def test_csv_schema_is_frozen_and_slotted() -> None:
    schema = CSV_SCHEMAS["orders.csv"]
    with pytest.raises(FrozenInstanceError):
        schema.filename = "changed.csv"  # type: ignore[misc]
    assert not hasattr(schema, "__dict__")


def test_allowed_values_are_immutable() -> None:
    values = CSV_SCHEMAS["orders.csv"].get_column("platform").allowed_values
    assert isinstance(values, frozenset)
    with pytest.raises(AttributeError):
        values.add("new-platform")  # type: ignore[union-attr]


def test_registry_is_immutable_mapping_proxy() -> None:
    assert isinstance(CSV_SCHEMAS, MappingProxyType)
    with pytest.raises(TypeError):
        CSV_SCHEMAS["extra.csv"] = CSV_SCHEMAS["orders.csv"]  # type: ignore[index]


@pytest.mark.parametrize("filename", sorted(REQUIRED_FILENAMES))
def test_column_names_property_preserves_documented_order(filename: str) -> None:
    schema = CSV_SCHEMAS[filename]
    assert schema.column_names == tuple(column.name for column in schema.columns)


def test_get_column_returns_requested_schema() -> None:
    column = CSV_SCHEMAS["payments.csv"].get_column("amount")
    assert isinstance(column, ColumnSchema)
    assert column.name == "amount"


def test_get_column_raises_descriptive_error_for_unknown_name() -> None:
    with pytest.raises(
        KeyError,
        match=r"Column 'missing' is not defined in schema 'orders\.csv'\.",
    ):
        CSV_SCHEMAS["orders.csv"].get_column("missing")


def test_registry_values_are_csv_schemas() -> None:
    assert all(isinstance(schema, CsvSchema) for schema in CSV_SCHEMAS.values())
