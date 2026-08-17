"""End-to-end orchestration tests for all reconciliation rules."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from kz_ecomops.reconciliation import (
    ReconciliationConfig,
    ReconciliationError,
    ReconciliationErrorCode,
    reconcile_dataset,
)
from kz_ecomops.validation import (
    DatasetValidationResult,
    validate_dataset_directory,
)


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = PROJECT_ROOT / "data" / "sample"
REFERENCE_AT = datetime(2026, 3, 20, 12, tzinfo=timezone.utc)


def _manifest() -> dict[str, object]:
    return json.loads((SAMPLE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _reference_for(scenario: dict[str, object]) -> datetime:
    value = scenario["reference_at"]
    return datetime.fromisoformat(value) if value else REFERENCE_AT  # type: ignore[arg-type]


def test_valid_normalized_dataset_produces_zero_anomalies() -> None:
    validation = validate_dataset_directory(SAMPLE_ROOT / "normalized" / "valid")

    result = reconcile_dataset(validation, REFERENCE_AT)

    assert result.reference_at == REFERENCE_AT
    assert result.config == ReconciliationConfig()
    assert not result.anomalies
    assert not result.not_evaluated


@pytest.mark.parametrize("scenario", _manifest()["scenarios"])
def test_every_manifest_scenario_produces_exactly_one_expected_anomaly(
    scenario: dict[str, object],
) -> None:
    validation = validate_dataset_directory(SAMPLE_ROOT / str(scenario["directory"]))

    result = reconcile_dataset(validation, _reference_for(scenario))

    assert len(result.anomalies) == scenario["expected_anomaly_count"] == 1
    assert result.anomalies[0].rule_code.value == scenario["code"]
    assert result.anomalies[0].anomaly_code.value == scenario["anomaly_code"]
    assert result.anomalies[0].order_id == scenario["affected_order_ids"][0]  # type: ignore[index]
    assert len({anomaly.anomaly_id for anomaly in result.anomalies}) == 1


def test_orchestration_is_repeatable_sorted_and_does_not_mutate_inputs() -> None:
    scenario = _manifest()["scenarios"][3]  # type: ignore[index]
    validation = validate_dataset_directory(SAMPLE_ROOT / scenario["directory"])  # type: ignore[index]
    assert validation.dataframes is not None
    originals = {
        filename: dataframe.copy(deep=True)
        for filename, dataframe in validation.dataframes.items()
    }
    config = ReconciliationConfig()

    first = reconcile_dataset(validation, REFERENCE_AT, config)
    second = reconcile_dataset(validation, REFERENCE_AT, config)

    assert first == second
    assert first.config is config
    assert tuple(anomaly.rule_code.value for anomaly in first.anomalies) == tuple(
        sorted(anomaly.rule_code.value for anomaly in first.anomalies)
    )
    for filename, dataframe in validation.dataframes.items():
        pd.testing.assert_frame_equal(dataframe, originals[filename])


def test_relationship_findings_do_not_block_rec10() -> None:
    scenario = _manifest()["scenarios"][-1]  # type: ignore[index]
    validation = validate_dataset_directory(SAMPLE_ROOT / scenario["directory"])  # type: ignore[index]
    assert validation.report.reconciliation_ready
    assert validation.report.relationship_finding_count == 1

    result = reconcile_dataset(validation, REFERENCE_AT)

    assert len(result.anomalies) == 1
    assert result.anomalies[0].rule_code.value == "REC-10"


def test_repeated_rec10_findings_are_grouped_without_duplicate_ids() -> None:
    validation = validate_dataset_directory(
        SAMPLE_ROOT / "scenarios" / "rec-10-cross-system-record-missing"
    )
    files = tuple(
        replace(file_report, messages=file_report.messages * 2)
        if file_report.relationship_finding_count
        else file_report
        for file_report in validation.report.files
    )
    repeated = replace(validation, report=replace(validation.report, files=files))

    result = reconcile_dataset(repeated, REFERENCE_AT)

    assert len(result.anomalies) == 1
    assert len({anomaly.anomaly_id for anomaly in result.anomalies}) == 1
    assert result.anomalies[0].rule_code.value == "REC-10"


def test_rejects_naive_reference_non_result_blocking_and_incomplete_data() -> None:
    valid = validate_dataset_directory(SAMPLE_ROOT / "normalized" / "valid")
    with pytest.raises(ValueError, match="timezone"):
        reconcile_dataset(valid, datetime(2026, 3, 20))
    with pytest.raises(TypeError, match="DatasetValidationResult"):
        reconcile_dataset({}, REFERENCE_AT)  # type: ignore[arg-type]

    blocking = validate_dataset_directory(
        SAMPLE_ROOT / "invalid" / "invalid-datetime"
    )
    with pytest.raises(ReconciliationError) as blocked:
        reconcile_dataset(blocking, REFERENCE_AT)
    assert blocked.value.code is ReconciliationErrorCode.NOT_RECONCILIATION_READY

    incomplete = DatasetValidationResult(
        report=valid.report,
        dataframes={
            filename: dataframe
            for filename, dataframe in valid.dataframes.items()  # type: ignore[union-attr]
            if filename != "refunds.csv"
        },
    )
    with pytest.raises(ReconciliationError) as missing:
        reconcile_dataset(incomplete, REFERENCE_AT)
    assert missing.value.code is ReconciliationErrorCode.INCOMPLETE_DATASET
