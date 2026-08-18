"""Streamlit AppTest coverage for the application shell."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from kz_ecomops.validation import CSV_SCHEMAS


PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = PROJECT_ROOT / "data" / "sample"


def _uploads(relative: str) -> list[tuple[str, bytes, str]]:
    directory = SAMPLE_ROOT / relative
    return [
        (filename, (directory / filename).read_bytes(), "text/csv")
        for filename in (
            "orders.csv",
            "payments.csv",
            "shipments.csv",
            "returns.csv",
            "refunds.csv",
        )
    ]


def _empty_uploads() -> list[tuple[str, bytes, str]]:
    return [
        (
            filename,
            (",".join(schema.column_names) + "\n").encode("utf-8"),
            "text/csv",
        )
        for filename, schema in CSV_SCHEMAS.items()
    ]


def _button(app: AppTest, label: str):
    return next(button for button in app.button if button.label == label)


def _selectbox(app: AppTest, label: str):
    return next(selectbox for selectbox in app.selectbox if selectbox.label == label)


def _text_input(app: AppTest, label: str):
    return next(text_input for text_input in app.text_input if text_input.label == label)


def _date_input(app: AppTest, label: str):
    return next(date_input for date_input in app.date_input if date_input.label == label)


def _multiselect(app: AppTest, label: str):
    return next(item for item in app.multiselect if item.label == label)


def _metric_values(app: AppTest) -> dict[str, str]:
    return {metric.label: str(metric.value) for metric in app.metric}


def _validated_app(tmp_path: Path, monkeypatch) -> tuple[AppTest, list[tuple[str, bytes, str]]]:
    monkeypatch.setenv("KZ_ECOMOPS_DB_PATH", str(tmp_path / "workflow.sqlite3"))
    uploads = _uploads("scenarios/rec-02-paid-not-shipped-on-time")
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=10)
    app.file_uploader[0].set_value(uploads).run(timeout=10)
    _button(app, "Validate dataset").click().run(timeout=10)
    assert app.session_state["validation_result"] is not None
    return app, uploads


def _reconciled_app(tmp_path: Path, monkeypatch) -> tuple[AppTest, list[tuple[str, bytes, str]]]:
    app, uploads = _validated_app(tmp_path, monkeypatch)
    _button(app, "Run reconciliation").click().run(timeout=10)
    assert app.session_state["reconciliation_result"] is not None
    return app, uploads


def test_app_starts_and_shows_upload_guidance() -> None:
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=10)

    assert not app.exception
    assert app.title[0].value == "KZ EcomOps Control Tower"
    assert any(
        "Multi-channel order reconciliation" in caption.value
        for caption in app.caption
    )
    assert any("synthetic or explicitly authorized" in info.value for info in app.info)
    assert len(app.file_uploader) == 1
    assert any("Missing files:" in warning.value for warning in app.warning)
    assert _button(app, "Run reconciliation").disabled
    assert len(app.download_button) == 0


def test_valid_upload_validation_reconciliation_and_review_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = tmp_path / "streamlit-test.sqlite3"
    monkeypatch.setenv("KZ_ECOMOPS_DB_PATH", str(database))
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=10)
    app.file_uploader[0].set_value(
        _uploads("scenarios/rec-02-paid-not-shipped-on-time")
    ).run(timeout=10)

    assert _button(app, "Run reconciliation").disabled
    _button(app, "Validate dataset").click().run(timeout=10)
    assert any("Ready for reconciliation" in item.value for item in app.success)
    assert not _button(app, "Run reconciliation").disabled
    metrics = {metric.label: str(metric.value) for metric in app.metric}
    assert metrics["Anomalies"] == "Not calculated"

    _button(app, "Run reconciliation").click().run(timeout=10)
    assert any("completed and saved successfully" in item.value for item in app.success)
    result = app.session_state["reconciliation_result"]
    assert result.anomalies[0].rule_code.value == "REC-02"
    metrics = {metric.label: str(metric.value) for metric in app.metric}
    assert metrics["Anomalies"] == "1"
    assert len(app.multiselect) == 4
    assert len(app.download_button) == 1
    download = app.download_button[0]
    assert download.label == "Download filtered anomalies CSV"
    assert download.proto.ignore_rerun
    assert any(
        "kz-ecomops-anomalies-20260320-120000Z.csv" in item.value
        for item in app.markdown
    )

    anomaly_id = result.anomalies[0].anomaly_id
    _selectbox(app, "Select an anomaly to inspect").set_value(anomaly_id).run(timeout=10)
    assert any(item.value == "Anomaly detail" for item in app.subheader)
    assert any("Compared values" in item.value for item in app.markdown)

    _selectbox(app, "Review status").set_value("resolved").run(timeout=10)
    _button(app, "Save review status").click().run(timeout=10)
    assert app.session_state["reconciliation_result"].anomalies[0].review_status.value == "resolved"

    _button(app, "Run reconciliation").click().run(timeout=10)
    assert app.session_state["reconciliation_result"].anomalies[0].review_status.value == "resolved"
    assert database.is_file()


def test_invalid_dataset_keeps_reconciliation_disabled() -> None:
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=10)
    app.file_uploader[0].set_value(
        _uploads("invalid/invalid-datetime")
    ).run(timeout=10)
    _button(app, "Validate dataset").click().run(timeout=10)

    assert any("Reconciliation not available" in item.value for item in app.error)
    assert _button(app, "Run reconciliation").disabled


def test_empty_header_only_dataset_does_not_crash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("KZ_ECOMOPS_DB_PATH", str(tmp_path / "empty.sqlite3"))
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=10)
    app.file_uploader[0].set_value(_empty_uploads()).run(timeout=10)
    _button(app, "Validate dataset").click().run(timeout=10)
    _button(app, "Run reconciliation").click().run(timeout=10)

    assert not app.exception
    metrics = {metric.label: str(metric.value) for metric in app.metric}
    assert metrics["Orders"] == "0"
    assert metrics["Order total"] == "0.00 EUR"
    assert metrics["Anomalies"] == "0"


@pytest.mark.parametrize(
    "selection_change",
    ("remove-one", "replace-content", "add-duplicate"),
)
def test_changed_upload_selection_invalidates_validated_state(
    tmp_path: Path,
    monkeypatch,
    selection_change: str,
) -> None:
    app, uploads = _validated_app(tmp_path, monkeypatch)
    assert not _button(app, "Run reconciliation").disabled

    changed = list(uploads)
    if selection_change == "remove-one":
        changed.pop()
    elif selection_change == "replace-content":
        filename, content, media_type = changed[0]
        changed[0] = (filename, content + b"\n", media_type)
    else:
        changed.append(uploads[0])
    app.file_uploader[0].set_value(changed).run(timeout=10)

    assert app.session_state["validation_result"] is None
    assert app.session_state["reconciliation_result"] is None
    assert app.session_state["persistence_outcome"] is None
    assert _button(app, "Run reconciliation").disabled
    assert _metric_values(app)["Anomalies"] == "Not calculated"
    assert not any("Ready for reconciliation" in item.value for item in app.success)
    assert len(app.multiselect) == 0
    assert len(app.download_button) == 0


def test_removing_all_uploads_invalidates_reconciled_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _ = _reconciled_app(tmp_path, monkeypatch)
    assert _metric_values(app)["Anomalies"] == "1"
    assert len(app.multiselect) == 4

    app.file_uploader[0].set_value([]).run(timeout=10)

    assert app.session_state["validation_result"] is None
    assert app.session_state["reconciliation_result"] is None
    assert app.session_state["persistence_outcome"] is None
    assert app.session_state["reconciliation_signature"] is None
    assert _button(app, "Run reconciliation").disabled
    assert _metric_values(app)["Anomalies"] == "Not calculated"
    assert len(app.multiselect) == 0
    assert len(app.download_button) == 0
    assert any("Missing files:" in warning.value for warning in app.warning)


@pytest.mark.parametrize(
    ("widget", "value"),
    (
        ("date", date(2026, 3, 21)),
        ("tolerance", "0.02"),
        ("high-threshold", "72"),
    ),
)
def test_configuration_change_invalidates_completed_result_without_rerunning(
    tmp_path: Path,
    monkeypatch,
    widget: str,
    value: object,
) -> None:
    app, _ = _reconciled_app(tmp_path, monkeypatch)
    assert app.session_state["persistence_outcome"] is not None

    if widget == "date":
        _date_input(app, "Reference date (UTC)").set_value(value).run(timeout=10)
    elif widget == "tolerance":
        _text_input(app, "Monetary tolerance (EUR)").set_value(value).run(timeout=10)
    else:
        _text_input(
            app,
            "High shipping delay threshold (whole hours, optional)",
        ).set_value(value).run(timeout=10)

    assert app.session_state["validation_result"] is not None
    assert app.session_state["reconciliation_result"] is None
    assert app.session_state["persistence_outcome"] is None
    assert app.session_state["reconciliation_signature"] is None
    assert not _button(app, "Run reconciliation").disabled
    assert _metric_values(app)["Anomalies"] == "Not calculated"
    assert len(app.multiselect) == 0
    assert len(app.download_button) == 0
    assert any(
        "Anomalies are not calculated" in info.value
        for info in app.info
    )


def test_rerun_after_configuration_change_uses_updated_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _ = _reconciled_app(tmp_path, monkeypatch)
    _date_input(app, "Reference date (UTC)").set_value(date(2026, 3, 21)).run(
        timeout=10
    )
    _text_input(app, "Monetary tolerance (EUR)").set_value("0.02").run(timeout=10)
    _text_input(
        app,
        "High shipping delay threshold (whole hours, optional)",
    ).set_value("72").run(timeout=10)
    assert app.session_state["reconciliation_result"] is None

    _button(app, "Run reconciliation").click().run(timeout=10)

    result = app.session_state["reconciliation_result"]
    assert result.reference_at.isoformat() == "2026-03-21T12:00:00+00:00"
    assert result.config.monetary_tolerance == Decimal("0.02")
    assert result.config.high_shipping_delay_threshold == timedelta(hours=72)
    assert app.session_state["reconciliation_signature"] is not None
    assert any(
        "Configuration used for this result" in item.value
        for item in app.markdown
    )


def test_filter_change_keeps_completed_result_current(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _ = _reconciled_app(tmp_path, monkeypatch)
    result = app.session_state["reconciliation_result"]
    signature = app.session_state["reconciliation_signature"]
    persistence = app.session_state["persistence_outcome"]

    _multiselect(app, "Filter by platform").set_value(["shopify"]).run(timeout=10)

    assert app.session_state["reconciliation_result"] == result
    assert app.session_state["reconciliation_signature"] == signature
    assert app.session_state["persistence_outcome"] == persistence
    assert _metric_values(app)["Anomalies"] == "1"
    assert len(app.download_button) == 1


def test_new_validation_always_invalidates_previous_reconciliation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _ = _reconciled_app(tmp_path, monkeypatch)

    _button(app, "Validate dataset").click().run(timeout=10)

    assert app.session_state["validation_result"] is not None
    assert app.session_state["reconciliation_result"] is None
    assert app.session_state["persistence_outcome"] is None
    assert _metric_values(app)["Anomalies"] == "Not calculated"
    assert len(app.download_button) == 0


def test_operational_distributions_follow_current_filters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _ = _reconciled_app(tmp_path, monkeypatch)
    metrics = _metric_values(app)

    assert metrics["All anomalies"] == "1"
    assert metrics["Filtered anomalies"] == "1"
    assert any(
        item.value == "Operational anomaly distributions"
        for item in app.subheader
    )

    _multiselect(app, "Filter by platform").set_value(["shopify"]).run(timeout=10)

    metrics = _metric_values(app)
    assert metrics["All anomalies"] == "1"
    assert metrics["Filtered anomalies"] == "1"
    assert app.session_state["reconciliation_result"] is not None


def test_zero_anomaly_result_downloads_header_only_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("KZ_ECOMOPS_DB_PATH", str(tmp_path / "empty-export.sqlite3"))
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=10)
    app.file_uploader[0].set_value(_empty_uploads()).run(timeout=10)
    _button(app, "Validate dataset").click().run(timeout=10)
    _button(app, "Run reconciliation").click().run(timeout=10)

    assert len(app.download_button) == 1
    assert any(
        "CSV will contain the header only" in info.value
        for info in app.info
    )
    assert any("Rows to export: **0**" in item.value for item in app.markdown)


def test_download_does_not_rerun_or_persist_business_workflow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _ = _reconciled_app(tmp_path, monkeypatch)
    result = app.session_state["reconciliation_result"]
    persistence = app.session_state["persistence_outcome"]

    app.download_button[0].click().run(timeout=10)

    assert app.session_state["reconciliation_result"] == result
    assert app.session_state["persistence_outcome"] == persistence
    assert len(app.download_button) == 1
