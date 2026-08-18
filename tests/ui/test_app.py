"""Streamlit AppTest coverage for the application shell."""

from __future__ import annotations

from pathlib import Path

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
