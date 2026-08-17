"""Tests for pure dashboard summaries, filters, and anomaly details."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from kz_ecomops.reconciliation import (
    ReconciliationConfig,
    ReconciliationResult,
    RuleCode,
    RuleNotEvaluated,
    reconcile_dataset,
)
from kz_ecomops.ui import (
    anomaly_detail,
    anomaly_table_rows,
    filter_anomalies,
    not_evaluated_rows,
    operational_summary,
)
from kz_ecomops.validation import validate_dataset_directory


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = PROJECT_ROOT / "data" / "sample"
REFERENCE_AT = datetime(2026, 3, 20, 12, tzinfo=timezone.utc)


def _result(relative: str):
    validation = validate_dataset_directory(SAMPLE_ROOT / relative)
    return validation, reconcile_dataset(validation, REFERENCE_AT)


def test_summary_distinguishes_not_calculated_from_real_zero() -> None:
    validation = validate_dataset_directory(SAMPLE_ROOT / "normalized" / "valid")

    before = operational_summary(None, None)
    validated = operational_summary(validation, None)
    completed = operational_summary(
        validation,
        ReconciliationResult(REFERENCE_AT, ReconciliationConfig()),
    )

    assert before["Anomalies"] == "Not calculated"
    assert validated["Reconciliation status"] == "Ready, not run"
    assert validated["Order total"].endswith(" EUR")
    assert completed["Anomalies"] == "0"
    assert completed["Checks not evaluated"] == "0"


def test_single_and_combined_filters_do_not_mutate_anomalies() -> None:
    _, first = _result("scenarios/rec-01-payment-amount-mismatch")
    _, second = _result("scenarios/rec-05-shipment-without-tracking")
    anomalies = (*first.anomalies, *second.anomalies)
    originals = tuple(anomalies)

    medium = filter_anomalies(anomalies, severities={"medium"})
    combined = filter_anomalies(
        anomalies,
        platforms={"shopify"},
        anomaly_codes={"SHIPMENT_WITHOUT_TRACKING"},
        severities={"medium"},
        review_statuses={"open"},
    )

    assert len(medium) == 1
    assert combined == second.anomalies
    assert tuple(anomalies) == originals


def test_anomaly_table_and_detail_include_accessible_severity_and_rf19_fields() -> None:
    _, result = _result("scenarios/rec-01-payment-amount-mismatch")
    anomaly = result.anomalies[0]

    row = anomaly_table_rows((anomaly,))[0]
    detail = anomaly_detail(anomaly)

    assert row["Severity"].startswith("⚠")
    assert row["Description"] == anomaly.description
    assert detail["Rule code"] == "REC-01"
    assert detail["Recommended action"] == anomaly.recommended_action
    assert detail["Compared values"]
    assert detail["Record references"]
    assert {"Filename", "Row number", "Record ID"} == set(
        detail["Record references"][0]
    )


def test_rule_not_evaluated_is_presented_separately_with_references() -> None:
    _, result = _result("scenarios/rec-07-return-received-not-refunded")
    reference = result.anomalies[0].record_references[0]
    unavailable = RuleNotEvaluated(
        RuleCode.REC_07,
        "shopify:ORDER-1",
        "shopify",
        "A refund cannot be associated unambiguously.",
        (reference,),
    )

    row = not_evaluated_rows((unavailable,))[0]

    assert row["Rule"] == "REC-07"
    assert "unambiguously" in row["Reason"]
    assert reference.filename in row["References"]


def test_presentation_does_not_modify_validation_dataframes() -> None:
    validation, result = _result("scenarios/rec-01-payment-amount-mismatch")
    assert validation.dataframes is not None
    originals = {
        filename: dataframe.copy(deep=True)
        for filename, dataframe in validation.dataframes.items()
    }

    operational_summary(validation, result)
    anomaly_table_rows(result.anomalies)
    anomaly_detail(result.anomalies[0])

    for filename, dataframe in validation.dataframes.items():
        pd.testing.assert_frame_equal(dataframe, originals[filename])
