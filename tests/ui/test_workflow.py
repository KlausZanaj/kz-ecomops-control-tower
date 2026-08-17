"""Pure workflow tests for validation and explicit reconciliation configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from kz_ecomops.ui import (
    REQUIRED_FILENAMES,
    build_reconciliation_config,
    reconcile_validation_result,
    upload_signature,
    validate_uploads,
)


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = PROJECT_ROOT / "data" / "sample"


@dataclass
class FakeUpload:
    name: str
    content: bytes

    def getvalue(self) -> bytes:
        return self.content


def _sample_uploads(relative: str) -> tuple[FakeUpload, ...]:
    directory = SAMPLE_ROOT / relative
    return tuple(
        FakeUpload(filename, (directory / filename).read_bytes())
        for filename in REQUIRED_FILENAMES
    )


def test_upload_signature_is_content_based_and_order_independent() -> None:
    uploads = _sample_uploads("normalized/valid")

    assert upload_signature(uploads) == upload_signature(tuple(reversed(uploads)))
    changed = (*uploads[:-1], FakeUpload(uploads[-1].name, b"changed"))
    assert upload_signature(uploads) != upload_signature(changed)


def test_valid_and_invalid_uploads_use_existing_validation_pipeline() -> None:
    valid = validate_uploads(_sample_uploads("normalized/valid"))
    invalid = validate_uploads(_sample_uploads("invalid/invalid-datetime"))

    assert valid.report.reconciliation_ready
    assert valid.dataframes is not None
    assert not invalid.report.reconciliation_ready
    assert invalid.dataframes is None


def test_config_parses_decimal_directly_and_requires_valid_thresholds() -> None:
    config = build_reconciliation_config("0.010", 48, 7, "72")

    assert config.monetary_tolerance == Decimal("0.010")
    assert config.shipping_limit == timedelta(hours=48)
    assert config.return_refund_limit == timedelta(days=7)
    assert config.high_shipping_delay_threshold == timedelta(hours=72)
    with pytest.raises(ValueError, match="valid decimal"):
        build_reconciliation_config("not-money", 48, 7, "")
    with pytest.raises(ValueError, match="strictly greater"):
        build_reconciliation_config("0.01", 48, 7, "48")


def test_validation_to_reconciliation_uses_explicit_utc_reference() -> None:
    validation = validate_uploads(
        _sample_uploads("scenarios/rec-02-paid-not-shipped-on-time")
    )
    config = build_reconciliation_config("0.01", 48, 7, "")

    result = reconcile_validation_result(
        validation,
        date(2026, 3, 4),
        time(12, 0),
        config,
    )

    assert result.reference_at.isoformat() == "2026-03-04T12:00:00+00:00"
    assert len(result.anomalies) == 1
    assert result.anomalies[0].rule_code.value == "REC-02"
