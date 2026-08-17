"""Tests for deterministic public synthetic sample datasets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kz_ecomops.sample_data import (
    PLATFORMS,
    build_sample_files,
    check_sample_data,
    generate_sample_data,
)
from kz_ecomops.validation import CSV_SCHEMAS, ValidationStage, validate_dataset_directory


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = PROJECT_ROOT / "data" / "sample"


def _manifest() -> dict[str, object]:
    return json.loads((SAMPLE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def test_committed_sample_tree_matches_deterministic_build() -> None:
    result = check_sample_data(SAMPLE_ROOT)

    assert result.is_current
    assert not result.missing_files
    assert not result.mismatched_files
    assert not result.unexpected_files


def test_generation_is_byte_for_byte_repeatable(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    assert generate_sample_data(first).is_current
    assert generate_sample_data(second).is_current

    expected = build_sample_files()
    assert {
        path: (first / path).read_bytes() for path in expected
    } == {
        path: (second / path).read_bytes() for path in expected
    }


def test_check_mode_does_not_overwrite_modified_file(tmp_path: Path) -> None:
    assert generate_sample_data(tmp_path).is_current
    target = tmp_path / "normalized" / "valid" / "orders.csv"
    target.write_text("changed\n", encoding="utf-8")
    before = target.read_bytes()

    result = check_sample_data(tmp_path)

    assert not result.is_current
    assert result.mismatched_files == ("normalized/valid/orders.csv",)
    assert target.read_bytes() == before
    with pytest.raises(FileExistsError, match="will not overwrite"):
        generate_sample_data(tmp_path)


def test_generator_refuses_unmanaged_files(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    unmanaged = tmp_path / "unmanaged.txt"
    unmanaged.write_text("keep me", encoding="utf-8")

    with pytest.raises(FileExistsError, match="unmanaged"):
        generate_sample_data(tmp_path)

    assert unmanaged.read_text(encoding="utf-8") == "keep me"


def test_manifest_directories_and_five_file_datasets_match() -> None:
    manifest = _manifest()
    declared = {
        manifest["canonical_valid_dataset"]["directory"],  # type: ignore[index]
        *(entry["directory"] for entry in manifest["scenarios"]),  # type: ignore[index]
        *(entry["directory"] for entry in manifest["invalid_examples"]),  # type: ignore[index]
    }
    actual = {
        path.parent.relative_to(SAMPLE_ROOT).as_posix()
        for path in SAMPLE_ROOT.rglob("orders.csv")
        if "sources" not in path.parts
    }

    assert declared == actual
    for directory in declared:
        assert {path.name for path in (SAMPLE_ROOT / directory).glob("*.csv")} == set(
            CSV_SCHEMAS
        )


def test_valid_dataset_covers_all_platforms_without_findings() -> None:
    result = validate_dataset_directory(SAMPLE_ROOT / "normalized" / "valid")

    assert result.report.reconciliation_ready
    assert result.report.blocking_message_count == 0
    assert result.report.relationship_finding_count == 0
    assert result.report.rejected_row_count == 0
    assert result.dataframes is not None
    assert set(result.dataframes["orders.csv"]["platform"]) == set(PLATFORMS)
    assert {
        value
        for filename, dataframe in result.dataframes.items()
        if "currency" in dataframe
        for value in dataframe["currency"]
    } == {"EUR"}


@pytest.mark.parametrize("scenario", _manifest()["scenarios"])
def test_rec_scenario_is_reconciliation_ready(scenario: dict[str, object]) -> None:
    result = validate_dataset_directory(SAMPLE_ROOT / str(scenario["directory"]))
    expected = scenario["expected_validation"]

    assert result.report.reconciliation_ready is expected["reconciliation_ready"]
    assert result.report.blocking_message_count == expected["blocking_message_count"]
    assert result.report.relationship_finding_count == expected["relationship_finding_count"]
    assert result.report.rejected_row_count == 0
    assert result.dataframes is not None


def test_rec05_preserves_empty_tracking() -> None:
    scenario = next(entry for entry in _manifest()["scenarios"] if entry["code"] == "REC-05")
    result = validate_dataset_directory(SAMPLE_ROOT / scenario["directory"])

    assert result.dataframes is not None
    shipment = result.dataframes["shipments.csv"].iloc[0]
    assert shipment["shipment_status"] == "shipped"
    assert shipment["tracking_number"] == ""
    assert shipment["shipped_at"]


def test_rec04_and_rec09_keep_intentional_duplicates() -> None:
    manifest = _manifest()
    rec04 = next(entry for entry in manifest["scenarios"] if entry["code"] == "REC-04")
    rec09 = next(entry for entry in manifest["scenarios"] if entry["code"] == "REC-09")

    payment_result = validate_dataset_directory(SAMPLE_ROOT / rec04["directory"])
    refund_result = validate_dataset_directory(SAMPLE_ROOT / rec09["directory"])

    assert payment_result.dataframes is not None
    assert refund_result.dataframes is not None
    assert len(payment_result.dataframes["payments.csv"]) == 2
    assert len(refund_result.dataframes["refunds.csv"]) == 2


@pytest.mark.parametrize("example", _manifest()["invalid_examples"])
def test_invalid_example_fails_at_documented_stage_and_code(
    example: dict[str, object],
) -> None:
    result = validate_dataset_directory(SAMPLE_ROOT / str(example["directory"]))

    assert not result.report.reconciliation_ready
    assert result.dataframes is None
    assert any(
        message.stage is ValidationStage(str(example["expected_stage"]))
        and message.code == example["expected_code"]
        and message.blocking
        for message in result.report.messages
    )


def test_samples_exclude_personal_and_real_business_fields() -> None:
    forbidden_fragments = (
        "customer_name",
        "first_name",
        "last_name",
        "email",
        "phone",
        "street_address",
        "api_key",
        "token",
        "password",
        "http://",
        "https://",
        "@",
    )

    for relative_path, content in build_sample_files().items():
        if not relative_path.endswith((".csv", ".json", ".md")):
            continue
        lowered = content.decode("utf-8").casefold()
        assert not any(fragment in lowered for fragment in forbidden_fragments)


def test_validating_samples_does_not_modify_any_committed_csv() -> None:
    csv_paths = tuple(SAMPLE_ROOT.rglob("*.csv"))
    before = {path: path.read_bytes() for path in csv_paths}
    manifest = _manifest()
    directories = [manifest["canonical_valid_dataset"]["directory"]]  # type: ignore[index]
    directories.extend(entry["directory"] for entry in manifest["scenarios"])  # type: ignore[index]
    directories.extend(entry["directory"] for entry in manifest["invalid_examples"])  # type: ignore[index]

    for directory in directories:
        validate_dataset_directory(SAMPLE_ROOT / directory)

    assert {path: path.read_bytes() for path in csv_paths} == before
