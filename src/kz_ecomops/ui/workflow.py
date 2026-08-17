"""UI orchestration that delegates all business work to existing public APIs."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation

from kz_ecomops.reconciliation import (
    ReconciliationConfig,
    ReconciliationResult,
    reconcile_dataset,
)
from kz_ecomops.validation import DatasetValidationResult, validate_dataset_directory

from .uploads import UploadedCsv, stage_uploads


def upload_signature(uploads: Iterable[UploadedCsv]) -> str:
    """Identify upload contents without retaining them or depending on input order."""

    items = sorted((upload.name, upload.getvalue()) for upload in uploads)
    digest = hashlib.sha256()
    for name, content in items:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def validate_uploads(uploads: Iterable[UploadedCsv]) -> DatasetValidationResult:
    """Validate staged uploads through the existing dataset validation API."""

    with stage_uploads(uploads) as directory:
        return validate_dataset_directory(directory)


def build_reconciliation_config(
    monetary_tolerance: str,
    shipping_hours: int,
    return_refund_days: int,
    high_delay_hours: str,
) -> ReconciliationConfig:
    """Parse user configuration without converting money through float."""

    try:
        tolerance = Decimal(monetary_tolerance.strip())
    except InvalidOperation as error:
        raise ValueError("Monetary tolerance must be a valid decimal value.") from error
    if isinstance(shipping_hours, bool) or not isinstance(shipping_hours, int):
        raise ValueError("Shipping limit must be a whole number of hours.")
    if isinstance(return_refund_days, bool) or not isinstance(return_refund_days, int):
        raise ValueError("Return-refund limit must be a whole number of days.")
    high_threshold = None
    if high_delay_hours.strip():
        try:
            high_hours = int(high_delay_hours.strip())
        except ValueError as error:
            raise ValueError(
                "High shipping delay threshold must be blank or a whole number of hours."
            ) from error
        high_threshold = timedelta(hours=high_hours)
    return ReconciliationConfig(
        monetary_tolerance=tolerance,
        shipping_limit=timedelta(hours=shipping_hours),
        return_refund_limit=timedelta(days=return_refund_days),
        high_shipping_delay_threshold=high_threshold,
    )


def reconcile_validation_result(
    validation_result: DatasetValidationResult,
    reference_date: date,
    reference_time: time,
    config: ReconciliationConfig,
) -> ReconciliationResult:
    """Run reconciliation with an explicit UTC reference timestamp."""

    reference_at = datetime.combine(reference_date, reference_time, tzinfo=timezone.utc)
    return reconcile_dataset(validation_result, reference_at, config)
