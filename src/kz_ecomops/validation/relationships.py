"""Non-blocking cross-file relationship findings for normalized CSV data."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from .integrity import CsvIntegrityValidationResult
from .schemas import CSV_SCHEMAS
from .uniqueness import CsvUniquenessValidationResult
from .values import CsvValueValidationResult


class CsvRelationshipFindingCode(StrEnum):
    """Stable codes for non-blocking cross-file relationship findings."""

    ORDER_REFERENCE_NOT_FOUND = "order_reference_not_found"
    ORDER_REFERENCE_DETAILS_MISMATCH = "order_reference_details_mismatch"
    RETURN_REFERENCE_NOT_FOUND = "return_reference_not_found"
    RETURN_REFERENCE_ORDER_MISMATCH = "return_reference_order_mismatch"
    PAYMENT_REFERENCE_NOT_FOUND = "payment_reference_not_found"
    PAYMENT_REFERENCE_ORDER_MISMATCH = "payment_reference_order_mismatch"


@dataclass(frozen=True, slots=True)
class CsvRelationshipFinding:
    """Describe one non-blocking relationship finding without retaining identifiers."""

    code: CsvRelationshipFindingCode
    filename: str
    row_number: int
    columns: tuple[str, ...]
    related_filename: str
    message: str


@dataclass(frozen=True, slots=True)
class CsvRelationshipValidationResult:
    """Contain non-blocking findings intended for future reconciliation rules."""

    findings: tuple[CsvRelationshipFinding, ...] = ()

    @property
    def has_findings(self) -> bool:
        """Return whether any relationship finding was produced."""

        return bool(self.findings)

    @property
    def finding_count(self) -> int:
        """Return the number of relationship findings."""

        return len(self.findings)

    @property
    def affected_records(self) -> frozenset[tuple[str, int]]:
        """Return unique filename and positional-row pairs with findings."""

        return frozenset(
            (finding.filename, finding.row_number) for finding in self.findings
        )

    @property
    def affected_record_count(self) -> int:
        """Return the number of distinct records with findings."""

        return len(self.affected_records)


def _finding(
    code: CsvRelationshipFindingCode,
    filename: str,
    row_number: int,
    columns: tuple[str, ...],
    related_filename: str,
    explanation: str,
) -> CsvRelationshipFinding:
    return CsvRelationshipFinding(
        code=code,
        filename=filename,
        row_number=row_number,
        columns=columns,
        related_filename=related_filename,
        message=(
            f"CSV file {filename!r}, data row {row_number}, column(s) "
            f"{', '.join(repr(column) for column in columns)}: {explanation} "
            f"Review the relationship with {related_filename!r}."
        ),
    )


def _validate_mapping_keys(name: str, mapping: object) -> Mapping[str, object]:
    if not isinstance(mapping, Mapping):
        raise TypeError(f"{name} must be a mapping keyed by CSV filename.")
    expected_filenames = set(CSV_SCHEMAS)
    actual_filenames = set(mapping)
    if actual_filenames != expected_filenames:
        missing = tuple(
            filename for filename in CSV_SCHEMAS if filename not in actual_filenames
        )
        extra = tuple(
            filename for filename in actual_filenames if filename not in expected_filenames
        )
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected: {', '.join(sorted(extra))}")
        raise ValueError(
            f"{name} must contain exactly the five registered CSV filenames "
            f"({'; '.join(details)})."
        )
    return mapping


def _validate_preconditions(
    dataframes: Mapping[str, pd.DataFrame],
    value_results: Mapping[str, CsvValueValidationResult],
    integrity_results: Mapping[str, CsvIntegrityValidationResult],
    uniqueness_results: Mapping[str, CsvUniquenessValidationResult],
) -> None:
    prerequisite = (
        "All value, integrity, and uniqueness validations must complete "
        "successfully before relationship validation."
    )
    for filename, schema in CSV_SCHEMAS.items():
        dataframe = dataframes[filename]
        if not isinstance(dataframe, pd.DataFrame):
            raise TypeError(f"dataframes[{filename!r}] must be a pandas DataFrame.")

        expected_results = (
            ("value_results", value_results[filename], CsvValueValidationResult),
            (
                "integrity_results",
                integrity_results[filename],
                CsvIntegrityValidationResult,
            ),
            (
                "uniqueness_results",
                uniqueness_results[filename],
                CsvUniquenessValidationResult,
            ),
        )
        for mapping_name, result, expected_type in expected_results:
            if not isinstance(result, expected_type):
                raise TypeError(
                    f"{mapping_name}[{filename!r}] must be a "
                    f"{expected_type.__name__}. {prerequisite}"
                )
            if result.schema != schema:
                raise ValueError(
                    f"{mapping_name}[{filename!r}] uses a different schema. "
                    f"{prerequisite}"
                )
            if result.row_count != len(dataframe):
                raise ValueError(
                    f"{mapping_name}[{filename!r}] has a different row count. "
                    f"{prerequisite}"
                )
            if not result.is_valid:
                raise ValueError(
                    f"{mapping_name}[{filename!r}] contains blocking problems. "
                    f"{prerequisite}"
                )


def _value(dataframe: pd.DataFrame, row_position: int, column: str) -> str:
    return dataframe.iloc[row_position, dataframe.columns.get_loc(column)]


def _is_empty(value: str) -> bool:
    return not value.strip()


def validate_csv_relationships(
    dataframes: Mapping[str, pd.DataFrame],
    value_results: Mapping[str, CsvValueValidationResult],
    integrity_results: Mapping[str, CsvIntegrityValidationResult],
    uniqueness_results: Mapping[str, CsvUniquenessValidationResult],
) -> CsvRelationshipValidationResult:
    """Find non-blocking cross-file reference problems after blocking validation."""

    checked_dataframes = _validate_mapping_keys("dataframes", dataframes)
    checked_value_results = _validate_mapping_keys("value_results", value_results)
    checked_integrity_results = _validate_mapping_keys(
        "integrity_results", integrity_results
    )
    checked_uniqueness_results = _validate_mapping_keys(
        "uniqueness_results", uniqueness_results
    )
    _validate_preconditions(
        checked_dataframes,  # type: ignore[arg-type]
        checked_value_results,  # type: ignore[arg-type]
        checked_integrity_results,  # type: ignore[arg-type]
        checked_uniqueness_results,  # type: ignore[arg-type]
    )

    orders = dataframes["orders.csv"]
    order_lookup = {
        _value(orders, position, "order_id"): (
            _value(orders, position, "platform"),
            _value(orders, position, "source_order_id"),
        )
        for position in range(len(orders))
    }

    returns = dataframes["returns.csv"]
    return_lookup = {
        _value(returns, position, "return_id"): _value(
            returns, position, "order_id"
        )
        for position in range(len(returns))
    }

    payments = dataframes["payments.csv"]
    payment_lookup: dict[str, list[str]] = {}
    for position in range(len(payments)):
        payment_lookup.setdefault(
            _value(payments, position, "payment_id"), []
        ).append(_value(payments, position, "order_id"))

    findings: list[CsvRelationshipFinding] = []
    linked_filenames = (
        "payments.csv",
        "shipments.csv",
        "returns.csv",
        "refunds.csv",
    )
    for filename in linked_filenames:
        dataframe = dataframes[filename]
        for row_position in range(len(dataframe)):
            row_number = row_position + 1
            order_id = _value(dataframe, row_position, "order_id")
            order_details = order_lookup.get(order_id)
            if order_details is None:
                findings.append(
                    _finding(
                        CsvRelationshipFindingCode.ORDER_REFERENCE_NOT_FOUND,
                        filename,
                        row_number,
                        ("order_id",),
                        "orders.csv",
                        "the referenced order does not exist.",
                    )
                )
            else:
                platform = _value(dataframe, row_position, "platform")
                source_order_id = _value(
                    dataframe, row_position, "source_order_id"
                )
                if order_details != (platform, source_order_id):
                    findings.append(
                        _finding(
                            CsvRelationshipFindingCode.ORDER_REFERENCE_DETAILS_MISMATCH,
                            filename,
                            row_number,
                            ("order_id", "platform", "source_order_id"),
                            "orders.csv",
                            "the order reference details do not match the order record.",
                        )
                    )

            if filename != "refunds.csv":
                continue

            return_id = _value(dataframe, row_position, "return_id") if "return_id" in dataframe.columns else ""
            if not _is_empty(return_id):
                related_order_id = return_lookup.get(return_id)
                if related_order_id is None:
                    findings.append(
                        _finding(
                            CsvRelationshipFindingCode.RETURN_REFERENCE_NOT_FOUND,
                            filename,
                            row_number,
                            ("return_id",),
                            "returns.csv",
                            "the referenced return does not exist.",
                        )
                    )
                elif related_order_id != order_id:
                    findings.append(
                        _finding(
                            CsvRelationshipFindingCode.RETURN_REFERENCE_ORDER_MISMATCH,
                            filename,
                            row_number,
                            ("return_id", "order_id"),
                            "returns.csv",
                            "the referenced return belongs to a different order.",
                        )
                    )

            payment_id = _value(dataframe, row_position, "payment_id") if "payment_id" in dataframe.columns else ""
            if not _is_empty(payment_id):
                related_order_ids = payment_lookup.get(payment_id)
                if related_order_ids is None:
                    findings.append(
                        _finding(
                            CsvRelationshipFindingCode.PAYMENT_REFERENCE_NOT_FOUND,
                            filename,
                            row_number,
                            ("payment_id",),
                            "payments.csv",
                            "the referenced payment does not exist.",
                        )
                    )
                elif order_id not in related_order_ids:
                    findings.append(
                        _finding(
                            CsvRelationshipFindingCode.PAYMENT_REFERENCE_ORDER_MISMATCH,
                            filename,
                            row_number,
                            ("payment_id", "order_id"),
                            "payments.csv",
                            "the referenced payment belongs only to different orders.",
                        )
                    )

    return CsvRelationshipValidationResult(findings=tuple(findings))
