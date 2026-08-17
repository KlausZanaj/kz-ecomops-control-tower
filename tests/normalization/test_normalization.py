"""Tests for the four documented synthetic source normalizers."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pandas as pd
import pytest

from kz_ecomops.normalization import (
    PLATFORM_MAPPINGS,
    SUPPORTED_SOURCE_PLATFORMS,
    NormalizationErrorCode,
    NormalizationIssue,
    NormalizationResult,
    normalize_all_platforms,
    normalize_platform_exports,
    normalize_source_dataframes,
    write_canonical_csvs,
)
from kz_ecomops.validation import CSV_SCHEMAS, DataType, validate_dataset_directory


PROJECT_ROOT = Path(__file__).parents[2]
SOURCE_ROOT = PROJECT_ROOT / "data" / "sample" / "sources"


def _source_frames(platform: str) -> dict[str, pd.DataFrame]:
    return {
        filename: pd.read_csv(
            SOURCE_ROOT / platform / filename,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
        )
        for filename in CSV_SCHEMAS
    }


@pytest.mark.parametrize("platform", sorted(SUPPORTED_SOURCE_PLATFORMS))
def test_normalizes_each_documented_platform(platform: str) -> None:
    result = normalize_platform_exports(SOURCE_ROOT / platform, platform)

    assert result.is_valid
    assert result.platforms == (platform,)
    assert result.dataframes is not None
    assert tuple(result.dataframes) == tuple(CSV_SCHEMAS)
    for filename, dataframe in result.dataframes.items():
        assert tuple(dataframe.columns) == CSV_SCHEMAS[filename].column_names
        assert len(dataframe) == 1
        assert all(
            isinstance(value, str)
            for value in dataframe.to_numpy().ravel()
        )
        assert dataframe.loc[0, "platform"] == platform
        assert dataframe.loc[0, "order_id"] == f"{platform}:{dataframe.loc[0, 'source_order_id']}"


@pytest.mark.parametrize("platform", sorted(SUPPORTED_SOURCE_PLATFORMS))
def test_platform_amounts_dates_and_currency_are_canonical(platform: str) -> None:
    result = normalize_platform_exports(SOURCE_ROOT / platform, platform)
    assert result.dataframes is not None

    for filename, dataframe in result.dataframes.items():
        schema = CSV_SCHEMAS[filename]
        for column in schema.columns:
            values = dataframe[column.name]
            if column.data_type is DataType.DECIMAL:
                assert all(not value or value == f"{Decimal(value):.2f}" for value in values)
            if column.data_type is DataType.DATETIME:
                assert all(not value or value.endswith("+00:00") for value in values)
        if "currency" in dataframe:
            assert set(dataframe["currency"]) <= {"EUR", ""}


@pytest.mark.parametrize("platform", sorted(SUPPORTED_SOURCE_PLATFORMS))
def test_status_mappings_cover_every_canonical_status(platform: str) -> None:
    mapping = PLATFORM_MAPPINGS[platform]

    for filename, schema in CSV_SCHEMAS.items():
        for column in schema.columns:
            if column.allowed_values is not None and "status" in column.name:
                assert set(mapping.status_mappings[filename][column.name].values()) == set(
                    column.allowed_values
                )


def test_rejects_unsupported_platform_without_exposing_input() -> None:
    private_value = "PRIVATE-PLATFORM-VALUE"
    result = normalize_source_dataframes({}, private_value)

    assert not result.is_valid
    assert result.issues[0].code is NormalizationErrorCode.UNSUPPORTED_PLATFORM
    assert private_value not in result.issues[0].message


def test_reports_all_missing_source_files(tmp_path: Path) -> None:
    result = normalize_platform_exports(tmp_path, "shopify")

    assert not result.is_valid
    assert result.dataframes is None
    assert [issue.code for issue in result.issues] == [
        NormalizationErrorCode.SOURCE_FILE_MISSING
    ] * len(CSV_SCHEMAS)


def test_reports_missing_source_column() -> None:
    frames = _source_frames("shopify")
    source_column = PLATFORM_MAPPINGS["shopify"].column_mappings["orders.csv"]["currency"]
    frames["orders.csv"] = frames["orders.csv"].drop(columns=[source_column])

    result = normalize_source_dataframes(frames, "shopify")

    assert result.dataframes is None
    assert result.issues[0].code is NormalizationErrorCode.SOURCE_COLUMN_MISSING
    assert result.issues[0].source_column == source_column


@pytest.mark.parametrize(
    ("canonical_column", "replacement", "expected_code"),
    [
        ("order_status", "undocumented", NormalizationErrorCode.UNKNOWN_STATUS),
        ("ordered_at", "not-a-date", NormalizationErrorCode.INVALID_DATETIME),
        ("order_total", "ambiguous-amount", NormalizationErrorCode.INVALID_AMOUNT),
        ("currency", "USD", NormalizationErrorCode.UNSUPPORTED_CURRENCY),
    ],
)
def test_reports_explicit_source_value_errors(
    canonical_column: str,
    replacement: str,
    expected_code: NormalizationErrorCode,
) -> None:
    frames = _source_frames("shopify")
    source_column = PLATFORM_MAPPINGS["shopify"].column_mappings["orders.csv"][canonical_column]
    frames["orders.csv"].loc[0, source_column] = replacement

    result = normalize_source_dataframes(frames, "shopify")

    assert result.dataframes is None
    assert any(issue.code is expected_code for issue in result.issues)
    assert replacement not in " ".join(issue.message for issue in result.issues)


def test_reports_non_string_source_value() -> None:
    frames = _source_frames("shopify")
    source_column = PLATFORM_MAPPINGS["shopify"].column_mappings["orders.csv"]["order_number"]
    frames["orders.csv"][source_column] = frames["orders.csv"][source_column].astype(object)
    frames["orders.csv"].loc[0, source_column] = 123

    result = normalize_source_dataframes(frames, "shopify")

    assert any(issue.code is NormalizationErrorCode.NON_STRING_VALUE for issue in result.issues)


@pytest.mark.parametrize("platform", sorted(SUPPORTED_SOURCE_PLATFORMS))
def test_does_not_modify_source_dataframes(platform: str) -> None:
    frames = _source_frames(platform)
    originals = {filename: dataframe.copy(deep=True) for filename, dataframe in frames.items()}

    normalize_source_dataframes(frames, platform)

    for filename in CSV_SCHEMAS:
        pd.testing.assert_frame_equal(frames[filename], originals[filename])


def test_does_not_modify_source_csv_files() -> None:
    paths = tuple(SOURCE_ROOT.rglob("*.csv"))
    before = {path: path.read_bytes() for path in paths}

    normalize_all_platforms(SOURCE_ROOT)

    assert {path: path.read_bytes() for path in paths} == before


def test_combines_four_platforms_and_validates_serialized_output(tmp_path: Path) -> None:
    result = normalize_all_platforms(SOURCE_ROOT)

    assert result.is_valid
    assert result.platforms == tuple(PLATFORM_MAPPINGS)
    assert result.dataframes is not None
    assert all(len(dataframe) == 4 for dataframe in result.dataframes.values())
    targets = write_canonical_csvs(result, tmp_path)
    validation = validate_dataset_directory(tmp_path)

    assert {path.name for path in targets} == set(CSV_SCHEMAS)
    assert validation.report.reconciliation_ready
    assert validation.report.relationship_finding_count == 0
    assert validation.dataframes is not None


def test_serialization_refuses_invalid_result_and_existing_files(tmp_path: Path) -> None:
    invalid = normalize_source_dataframes({}, "not-supported")
    with pytest.raises(ValueError, match="valid normalization"):
        write_canonical_csvs(invalid, tmp_path)

    valid = normalize_all_platforms(SOURCE_ROOT)
    assert valid.is_valid
    (tmp_path / "orders.csv").write_text("keep\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="will not overwrite"):
        write_canonical_csvs(valid, tmp_path)
    assert (tmp_path / "orders.csv").read_text(encoding="utf-8") == "keep\n"


def test_public_results_and_mappings_are_immutable_and_protected() -> None:
    result = normalize_all_platforms(SOURCE_ROOT)
    assert isinstance(result.dataframes, MappingProxyType)
    assert isinstance(PLATFORM_MAPPINGS, MappingProxyType)
    assert isinstance(PLATFORM_MAPPINGS["shopify"].column_mappings, MappingProxyType)

    with pytest.raises(FrozenInstanceError):
        result.platforms = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        PLATFORM_MAPPINGS["extra"] = PLATFORM_MAPPINGS["shopify"]  # type: ignore[index]


def test_normalization_issue_is_frozen_and_slotted() -> None:
    issue = NormalizationIssue(
        code=NormalizationErrorCode.INVALID_AMOUNT,
        platform="shopify",
        filename="orders.csv",
        row_number=1,
        source_column="sh_total_amount",
        message="Correct the synthetic amount.",
    )

    with pytest.raises(FrozenInstanceError):
        issue.row_number = 2  # type: ignore[misc]
    assert not hasattr(issue, "__dict__")


def test_normalization_error_codes_are_exact() -> None:
    assert {code.value for code in NormalizationErrorCode} == {
        "unsupported_platform",
        "source_file_missing",
        "source_read_error",
        "source_column_missing",
        "non_string_value",
        "unknown_status",
        "invalid_datetime",
        "invalid_amount",
        "unsupported_currency",
    }
