"""Normalize documented synthetic platform exports into canonical DataFrames."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

import pandas as pd

from kz_ecomops.validation import CSV_SCHEMAS, DataType

from .mappings import (
    PLATFORM_MAPPINGS,
    PlatformMapping,
    SourceAmountStyle,
    SourceDateStyle,
)


class NormalizationErrorCode(StrEnum):
    """Stable error codes for synthetic source normalization."""

    UNSUPPORTED_PLATFORM = "unsupported_platform"
    SOURCE_FILE_MISSING = "source_file_missing"
    SOURCE_READ_ERROR = "source_read_error"
    SOURCE_COLUMN_MISSING = "source_column_missing"
    NON_STRING_VALUE = "non_string_value"
    UNKNOWN_STATUS = "unknown_status"
    INVALID_DATETIME = "invalid_datetime"
    INVALID_AMOUNT = "invalid_amount"
    UNSUPPORTED_CURRENCY = "unsupported_currency"


@dataclass(frozen=True, slots=True)
class NormalizationIssue:
    """Describe one source normalization problem without retaining source values."""

    code: NormalizationErrorCode
    platform: str
    filename: str
    row_number: int | None
    source_column: str | None
    message: str


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """Contain protected canonical DataFrames or deterministic issues."""

    platforms: tuple[str, ...]
    dataframes: Mapping[str, pd.DataFrame] | None
    issues: tuple[NormalizationIssue, ...] = ()

    def __post_init__(self) -> None:
        if self.dataframes is not None:
            object.__setattr__(
                self,
                "dataframes",
                MappingProxyType(
                    {
                        filename: dataframe.copy(deep=True)
                        for filename, dataframe in self.dataframes.items()
                    }
                ),
            )

    @property
    def is_valid(self) -> bool:
        return self.dataframes is not None and not self.issues

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def total_row_count(self) -> int:
        if self.dataframes is None:
            return 0
        return sum(len(dataframe) for dataframe in self.dataframes.values())


def _issue(
    code: NormalizationErrorCode,
    platform: str,
    filename: str,
    explanation: str,
    *,
    row_number: int | None = None,
    source_column: str | None = None,
) -> NormalizationIssue:
    location = f"Synthetic {platform} export {filename!r}"
    if row_number is not None:
        location += f", data row {row_number}"
    if source_column is not None:
        location += f", source column {source_column!r}"
    return NormalizationIssue(
        code=code,
        platform=platform,
        filename=filename,
        row_number=row_number,
        source_column=source_column,
        message=f"{location}: {explanation}",
    )


def _normalize_amount(value: str, mapping: PlatformMapping) -> str | None:
    if mapping.amount_style is SourceAmountStyle.INTEGER_CENTS:
        if re.fullmatch(r"-?\d+", value) is None:
            return None
        decimal_value = Decimal(value) / Decimal("100")
    else:
        decimal_text = value.replace(",", ".") if mapping.amount_style is SourceAmountStyle.COMMA_DECIMAL else value
        if re.fullmatch(r"-?\d+(?:\.\d{1,2})?", decimal_text) is None:
            return None
        try:
            decimal_value = Decimal(decimal_text)
        except InvalidOperation:
            return None
    if not decimal_value.is_finite():
        return None
    return f"{decimal_value:.2f}"


def _matches_date_style(value: str, style: SourceDateStyle) -> bool:
    if style is SourceDateStyle.ISO_OFFSET:
        return "T" in value and not value.endswith("Z") and re.search(r"[+-]\d{2}:\d{2}$", value) is not None
    if style is SourceDateStyle.ISO_ZULU:
        return "T" in value and value.endswith("Z")
    if style is SourceDateStyle.SPACE_OFFSET:
        return " " in value and re.search(r"[+-]\d{2}:\d{2}$", value) is not None
    return re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[+-]\d{4}", value) is not None


def _normalize_datetime(value: str, mapping: PlatformMapping) -> str | None:
    if not _matches_date_style(value, mapping.date_style):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.isoformat(timespec="seconds")


def _normalize_file(
    source: pd.DataFrame,
    filename: str,
    mapping: PlatformMapping,
) -> tuple[pd.DataFrame | None, list[NormalizationIssue]]:
    schema = CSV_SCHEMAS[filename]
    columns = mapping.column_mappings[filename]
    missing = tuple(
        source_column
        for source_column in columns.values()
        if source_column not in source.columns
    )
    if missing:
        return None, [
            _issue(
                NormalizationErrorCode.SOURCE_COLUMN_MISSING,
                mapping.platform,
                filename,
                "the documented simulated source column is missing.",
                source_column=column,
            )
            for column in missing
        ]

    normalized_rows: list[dict[str, str]] = []
    issues: list[NormalizationIssue] = []
    for row_position in range(len(source)):
        row_number = row_position + 1
        normalized = {column: "" for column in schema.column_names}
        normalized["platform"] = mapping.platform
        for column in schema.columns:
            canonical_name = column.name
            if canonical_name in {"platform", "order_id"}:
                continue
            source_column = columns[canonical_name]
            value = source.iloc[row_position, source.columns.get_loc(source_column)]
            if not isinstance(value, str):
                issues.append(
                    _issue(
                        NormalizationErrorCode.NON_STRING_VALUE,
                        mapping.platform,
                        filename,
                        "the source value must remain text during normalization.",
                        row_number=row_number,
                        source_column=source_column,
                    )
                )
                continue
            if not value:
                normalized[canonical_name] = ""
                continue
            status_mapping = mapping.status_mappings[filename].get(canonical_name)
            if status_mapping is not None:
                canonical_status = status_mapping.get(value)
                if canonical_status is None:
                    issues.append(
                        _issue(
                            NormalizationErrorCode.UNKNOWN_STATUS,
                            mapping.platform,
                            filename,
                            "the status is not in the documented simulated mapping.",
                            row_number=row_number,
                            source_column=source_column,
                        )
                    )
                    continue
                normalized[canonical_name] = canonical_status
            elif canonical_name == "currency":
                if value != "EUR":
                    issues.append(
                        _issue(
                            NormalizationErrorCode.UNSUPPORTED_CURRENCY,
                            mapping.platform,
                            filename,
                            "only EUR is supported by the MVP normalization pipeline.",
                            row_number=row_number,
                            source_column=source_column,
                        )
                    )
                    continue
                normalized[canonical_name] = value
            elif column.data_type is DataType.DECIMAL:
                amount = _normalize_amount(value, mapping)
                if amount is None:
                    issues.append(
                        _issue(
                            NormalizationErrorCode.INVALID_AMOUNT,
                            mapping.platform,
                            filename,
                            "the amount cannot be normalized without ambiguity.",
                            row_number=row_number,
                            source_column=source_column,
                        )
                    )
                    continue
                normalized[canonical_name] = amount
            elif column.data_type is DataType.DATETIME:
                normalized_date = _normalize_datetime(value, mapping)
                if normalized_date is None:
                    issues.append(
                        _issue(
                            NormalizationErrorCode.INVALID_DATETIME,
                            mapping.platform,
                            filename,
                            "the date-time cannot be normalized with a verified timezone.",
                            row_number=row_number,
                            source_column=source_column,
                        )
                    )
                    continue
                normalized[canonical_name] = normalized_date
            else:
                normalized[canonical_name] = value
        source_order_id = normalized["source_order_id"]
        normalized["order_id"] = f"{mapping.platform}:{source_order_id}"
        normalized_rows.append(normalized)

    if issues:
        return None, issues
    dataframe = pd.DataFrame(normalized_rows, columns=schema.column_names, dtype=str)
    return dataframe, []


def normalize_source_dataframes(
    source_dataframes: Mapping[str, pd.DataFrame],
    platform: str,
) -> NormalizationResult:
    """Normalize five in-memory simulated source exports without modifying them."""

    mapping = PLATFORM_MAPPINGS.get(platform)
    if mapping is None:
        return NormalizationResult(
            platforms=(),
            dataframes=None,
            issues=(
                NormalizationIssue(
                    code=NormalizationErrorCode.UNSUPPORTED_PLATFORM,
                    platform="",
                    filename="",
                    row_number=None,
                    source_column=None,
                    message="The requested source platform is not supported.",
                ),
            ),
        )
    if not isinstance(source_dataframes, Mapping):
        raise TypeError("source_dataframes must be a mapping keyed by CSV filename.")

    missing_files = tuple(
        filename for filename in CSV_SCHEMAS if filename not in source_dataframes
    )
    if missing_files:
        return NormalizationResult(
            platforms=(platform,),
            dataframes=None,
            issues=tuple(
                _issue(
                    NormalizationErrorCode.SOURCE_FILE_MISSING,
                    platform,
                    filename,
                    "the required simulated source file is missing.",
                )
                for filename in missing_files
            ),
        )

    normalized: dict[str, pd.DataFrame] = {}
    issues: list[NormalizationIssue] = []
    for filename in CSV_SCHEMAS:
        source = source_dataframes[filename]
        if not isinstance(source, pd.DataFrame):
            raise TypeError(f"source_dataframes[{filename!r}] must be a pandas DataFrame.")
        dataframe, file_issues = _normalize_file(source, filename, mapping)
        issues.extend(file_issues)
        if dataframe is not None:
            normalized[filename] = dataframe
    return NormalizationResult(
        platforms=(platform,),
        dataframes=normalized if not issues else None,
        issues=tuple(issues),
    )


def normalize_platform_exports(
    source_directory: str | Path,
    platform: str,
) -> NormalizationResult:
    """Read and normalize one directory of documented simulated exports."""

    if platform not in PLATFORM_MAPPINGS:
        return normalize_source_dataframes({}, platform)
    directory = Path(source_directory)
    source_dataframes: dict[str, pd.DataFrame] = {}
    issues: list[NormalizationIssue] = []
    for filename in CSV_SCHEMAS:
        path = directory / filename
        if not path.is_file():
            issues.append(
                _issue(
                    NormalizationErrorCode.SOURCE_FILE_MISSING,
                    platform,
                    filename,
                    "the required simulated source file is missing.",
                )
            )
            continue
        try:
            source_dataframes[filename] = pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                na_filter=False,
                index_col=False,
            )
        except (OSError, pd.errors.ParserError, UnicodeDecodeError):
            issues.append(
                _issue(
                    NormalizationErrorCode.SOURCE_READ_ERROR,
                    platform,
                    filename,
                    "the simulated source file could not be read safely.",
                )
            )
    if issues:
        return NormalizationResult(
            platforms=(platform,), dataframes=None, issues=tuple(issues)
        )
    return normalize_source_dataframes(source_dataframes, platform)


def normalize_all_platforms(source_root: str | Path) -> NormalizationResult:
    """Normalize and combine the four simulated platform directories."""

    root = Path(source_root)
    results = [
        normalize_platform_exports(root / platform, platform)
        for platform in PLATFORM_MAPPINGS
    ]
    issues = tuple(issue for result in results for issue in result.issues)
    if issues:
        return NormalizationResult(
            platforms=tuple(PLATFORM_MAPPINGS), dataframes=None, issues=issues
        )
    combined = {
        filename: pd.concat(
            [result.dataframes[filename] for result in results],  # type: ignore[index]
            ignore_index=True,
        ).loc[:, CSV_SCHEMAS[filename].column_names]
        for filename in CSV_SCHEMAS
    }
    return NormalizationResult(
        platforms=tuple(PLATFORM_MAPPINGS), dataframes=combined
    )


def write_canonical_csvs(
    result: NormalizationResult,
    destination: str | Path,
) -> tuple[Path, ...]:
    """Serialize a valid result without overwriting existing canonical files."""

    if not isinstance(result, NormalizationResult):
        raise TypeError("result must be a NormalizationResult.")
    if not result.is_valid or result.dataframes is None:
        raise ValueError("A valid normalization result is required for serialization.")
    root = Path(destination)
    targets = tuple(root / filename for filename in CSV_SCHEMAS)
    if any(target.exists() for target in targets):
        raise FileExistsError("Canonical CSV serialization will not overwrite existing files.")
    root.mkdir(parents=True, exist_ok=True)
    for filename, target in zip(CSV_SCHEMAS, targets, strict=True):
        result.dataframes[filename].to_csv(
            target,
            index=False,
            encoding="utf-8",
            lineterminator="\n",
        )
    return targets
