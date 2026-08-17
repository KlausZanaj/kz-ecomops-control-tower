"""Deterministic orchestration for all ten reconciliation rules."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from enum import StrEnum

import pandas as pd

from kz_ecomops.validation import CSV_SCHEMAS, DatasetValidationResult

from .context import ReconciliationContext
from .domain import (
    ReconciliationAnomaly,
    ReconciliationConfig,
    ReconciliationResult,
)
from .rules_01_05 import (
    evaluate_rec_01,
    evaluate_rec_02,
    evaluate_rec_03,
    evaluate_rec_04,
    evaluate_rec_05,
)
from .rules_06_10 import (
    evaluate_rec_06,
    evaluate_rec_07,
    evaluate_rec_08,
    evaluate_rec_09,
    evaluate_rec_10,
)


class ReconciliationErrorCode(StrEnum):
    """Stable codes for rejected reconciliation executions."""

    INVALID_RESULT = "invalid_result"
    INCOMPLETE_DATASET = "incomplete_dataset"
    NOT_RECONCILIATION_READY = "not_reconciliation_ready"


class ReconciliationError(ValueError):
    """Report a safe reconciliation precondition failure."""

    def __init__(self, code: ReconciliationErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def _merge_duplicate_anomalies(
    anomalies: tuple[ReconciliationAnomaly, ...],
) -> tuple[ReconciliationAnomaly, ...]:
    """Group repeated business anomalies while retaining current row references."""

    grouped: dict[str, ReconciliationAnomaly] = {}
    for anomaly in anomalies:
        existing = grouped.get(anomaly.anomaly_id)
        if existing is None:
            grouped[anomaly.anomaly_id] = anomaly
            continue
        references = {
            (
                reference.filename,
                reference.row_number,
                reference.record_id,
            ): reference
            for reference in (*existing.record_references, *anomaly.record_references)
        }
        grouped[anomaly.anomaly_id] = replace(
            existing,
            record_references=tuple(references.values()),
        )
    return tuple(grouped.values())


def _validated_dataframes(
    validation_result: object,
) -> dict[str, pd.DataFrame]:
    if not isinstance(validation_result, DatasetValidationResult):
        raise TypeError("validation_result must be a DatasetValidationResult.")
    if (
        not validation_result.report.reconciliation_ready
        or validation_result.report.blocking_message_count
    ):
        raise ReconciliationError(
            ReconciliationErrorCode.NOT_RECONCILIATION_READY,
            "Reconciliation requires a complete validation result without blocking messages.",
        )
    if validation_result.dataframes is None:
        raise ReconciliationError(
            ReconciliationErrorCode.INCOMPLETE_DATASET,
            "The validation result does not expose the five canonical DataFrames.",
        )
    if set(validation_result.dataframes) != set(CSV_SCHEMAS):
        raise ReconciliationError(
            ReconciliationErrorCode.INCOMPLETE_DATASET,
            "The validation result must contain exactly the five canonical DataFrames.",
        )
    checked: dict[str, pd.DataFrame] = {}
    for filename in CSV_SCHEMAS:
        dataframe = validation_result.dataframes[filename]
        if not isinstance(dataframe, pd.DataFrame):
            raise ReconciliationError(
                ReconciliationErrorCode.INCOMPLETE_DATASET,
                f"The canonical entry {filename!r} is not a pandas DataFrame.",
            )
        report = validation_result.report.get_file(filename)
        if (
            report.row_count != len(dataframe)
            or report.accepted_row_count != len(dataframe)
            or report.rejected_row_count
        ):
            raise ReconciliationError(
                ReconciliationErrorCode.INVALID_RESULT,
                "Validation report counts do not match the canonical DataFrames.",
            )
        checked[filename] = dataframe
    return checked


def reconcile_dataset(
    validation_result: DatasetValidationResult,
    reference_at: datetime,
    config: ReconciliationConfig | None = None,
) -> ReconciliationResult:
    """Run REC-01 through REC-10 in stable order on a ready validated dataset."""

    if not isinstance(reference_at, datetime):
        raise TypeError("reference_at must be a datetime.")
    if reference_at.tzinfo is None or reference_at.utcoffset() is None:
        raise ValueError("reference_at must include a timezone.")
    effective_config = ReconciliationConfig() if config is None else config
    if not isinstance(effective_config, ReconciliationConfig):
        raise TypeError("config must be a ReconciliationConfig or None.")
    dataframes = _validated_dataframes(validation_result)
    context = ReconciliationContext.from_dataframes(dataframes)
    relationship_messages = tuple(validation_result.report.messages)

    evaluations = (
        evaluate_rec_01(context, reference_at, effective_config),
        evaluate_rec_02(context, reference_at, effective_config),
        evaluate_rec_03(context, reference_at, effective_config),
        evaluate_rec_04(context, reference_at, effective_config),
        evaluate_rec_05(context, reference_at, effective_config),
        evaluate_rec_06(context, reference_at, effective_config),
        evaluate_rec_07(context, reference_at, effective_config),
        evaluate_rec_08(context, reference_at, effective_config),
        evaluate_rec_09(context, reference_at, effective_config),
        evaluate_rec_10(
            context,
            relationship_messages,
            reference_at,
            effective_config,
        ),
    )
    anomalies = tuple(
        anomaly
        for evaluation in evaluations
        for anomaly in evaluation.anomalies
    )
    return ReconciliationResult(
        reference_at=reference_at,
        config=effective_config,
        anomalies=_merge_duplicate_anomalies(anomalies),
        not_evaluated=tuple(
            unavailable
            for evaluation in evaluations
            for unavailable in evaluation.not_evaluated
        ),
    )


__all__ = [
    "ReconciliationError",
    "ReconciliationErrorCode",
    "reconcile_dataset",
]
