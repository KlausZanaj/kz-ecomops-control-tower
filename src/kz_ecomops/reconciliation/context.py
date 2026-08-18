"""Private one-pass indexes shared by reconciliation rules."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import pandas as pd

from kz_ecomops.validation import CSV_SCHEMAS

from .domain import RecordReference


@dataclass(frozen=True, slots=True)
class IndexedRecord:
    """Hold an immutable row snapshot and its deterministic source reference."""

    values: Mapping[str, str]
    reference: RecordReference

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def get(self, column: str) -> str:
        return self.values.get(column, "")


def _record_identifier(filename: str, values: Mapping[str, str]) -> str:
    identifier_columns = {
        "orders.csv": ("order_id",),
        "payments.csv": ("payment_id", "provider_transaction_id"),
        "shipments.csv": ("shipment_id",),
        "returns.csv": ("return_id",),
        "refunds.csv": ("refund_id", "provider_refund_id"),
    }[filename]
    identifiers = tuple(values.get(column, "").strip() for column in identifier_columns)
    available = tuple(value for value in identifiers if value)
    if available:
        return "|".join(available)
    material = json.dumps(
        dict(sorted(values.items())),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"content-{hashlib.sha256(material).hexdigest()}"


def _freeze_grouped(
    grouped: Mapping[str, list[IndexedRecord]],
) -> Mapping[str, tuple[IndexedRecord, ...]]:
    return MappingProxyType(
        {
            key: tuple(records)
            for key, records in sorted(grouped.items())
        }
    )


@dataclass(frozen=True, slots=True)
class ReconciliationContext:
    """Index a complete dataset once for reuse by all ten rules."""

    records_by_file: Mapping[str, tuple[IndexedRecord, ...]]
    orders_by_id: Mapping[str, IndexedRecord]
    records_by_order: Mapping[str, Mapping[str, tuple[IndexedRecord, ...]]]
    returns_by_id: Mapping[str, IndexedRecord]
    payments_by_id: Mapping[str, tuple[IndexedRecord, ...]]

    @classmethod
    def from_dataframes(
        cls,
        dataframes: Mapping[str, pd.DataFrame],
    ) -> ReconciliationContext:
        """Snapshot strings and build every order/identifier lookup in one pass."""

        if set(dataframes) != set(CSV_SCHEMAS):
            raise ValueError("dataframes must contain exactly the five canonical CSV files.")

        records_by_file: dict[str, tuple[IndexedRecord, ...]] = {}
        grouped_by_order: dict[str, dict[str, list[IndexedRecord]]] = {
            filename: {} for filename in CSV_SCHEMAS if filename != "orders.csv"
        }
        orders_by_id: dict[str, IndexedRecord] = {}
        returns_by_id: dict[str, IndexedRecord] = {}
        payments_by_id: dict[str, list[IndexedRecord]] = {}

        for filename in CSV_SCHEMAS:
            dataframe = dataframes[filename]
            if not isinstance(dataframe, pd.DataFrame):
                raise TypeError(f"dataframes[{filename!r}] must be a pandas DataFrame.")
            records: list[IndexedRecord] = []
            column_names = tuple(str(column) for column in dataframe.columns)
            for row_number, row_values in enumerate(
                dataframe.itertuples(index=False, name=None),
                start=1,
            ):
                values = dict(zip(column_names, row_values, strict=True))
                if any(not isinstance(value, str) for value in values.values()):
                    raise TypeError("Canonical reconciliation values must remain strings.")
                record = IndexedRecord(
                    values=values,
                    reference=RecordReference(
                        filename=filename,
                        row_number=row_number,
                        record_id=_record_identifier(filename, values),
                    ),
                )
                records.append(record)
                order_id = record.get("order_id")
                if filename == "orders.csv":
                    orders_by_id[order_id] = record
                else:
                    grouped_by_order[filename].setdefault(order_id, []).append(record)
                if filename == "returns.csv":
                    returns_by_id[record.get("return_id")] = record
                elif filename == "payments.csv":
                    payments_by_id.setdefault(record.get("payment_id"), []).append(record)
            records_by_file[filename] = tuple(records)

        return cls(
            records_by_file=MappingProxyType(records_by_file),
            orders_by_id=MappingProxyType(dict(sorted(orders_by_id.items()))),
            records_by_order=MappingProxyType(
                {
                    filename: _freeze_grouped(groups)
                    for filename, groups in grouped_by_order.items()
                }
            ),
            returns_by_id=MappingProxyType(dict(sorted(returns_by_id.items()))),
            payments_by_id=_freeze_grouped(payments_by_id),
        )

    def for_order(self, filename: str, order_id: str) -> tuple[IndexedRecord, ...]:
        return self.records_by_order[filename].get(order_id, ())
