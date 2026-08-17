"""Streamlit application shell and upload foundation."""

from __future__ import annotations

from datetime import date, time

import streamlit as st

from kz_ecomops.validation import ValidationMessage, ValidationStage

from .uploads import REQUIRED_FILENAMES, inspect_uploads
from .presentation import (
    anomaly_detail,
    anomaly_table_rows,
    filter_anomalies,
    not_evaluated_rows,
    operational_summary,
)
from .workflow import (
    build_reconciliation_config,
    reconcile_validation_result,
    upload_signature,
    validate_uploads,
)


TITLE = "KZ EcomOps Control Tower"
SUBTITLE = "Multi-channel order reconciliation and e-commerce operations analytics."


def _initialize_state() -> None:
    defaults = {
        "validation_result": None,
        "reconciliation_result": None,
        "upload_signature": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _message_rows(messages: tuple[ValidationMessage, ...]) -> list[dict[str, str]]:
    return [
        {
            "Stage": message.stage.value,
            "Code": message.code,
            "File": message.filename,
            "Rows": ", ".join(map(str, message.row_numbers)) or "—",
            "Columns": ", ".join(message.columns) or "—",
            "Explanation": message.message,
        }
        for message in messages
    ]


def _render_validation_report() -> None:
    result = st.session_state.validation_result
    if result is None:
        st.info("Validation has not been run for this upload selection.")
        return
    report = result.report
    st.subheader("Validation report")
    total, accepted, rejected = st.columns(3)
    total.metric("Records processed", report.total_row_count)
    accepted.metric("Records accepted", report.accepted_row_count)
    rejected.metric("Records rejected", report.rejected_row_count)
    st.dataframe(
        [
            {
                "File": file_report.filename,
                "Processed": file_report.row_count,
                "Accepted": file_report.accepted_row_count,
                "Rejected": file_report.rejected_row_count,
            }
            for file_report in report.files
        ],
        hide_index=True,
        width="stretch",
    )
    blocking = tuple(message for message in report.messages if message.blocking)
    relationships = tuple(
        message
        for message in report.messages
        if message.stage is ValidationStage.RELATIONSHIP and not message.blocking
    )
    if blocking:
        st.error("Blocking validation problems must be corrected before reconciliation.")
        st.dataframe(_message_rows(blocking), hide_index=True, width="stretch")
    else:
        st.success("No blocking validation problems were found.")
    if relationships:
        st.warning("Non-blocking relationship findings will be evaluated by REC-10.")
        st.dataframe(
            _message_rows(relationships),
            hide_index=True,
            width="stretch",
        )
    if report.reconciliation_ready:
        st.success("Ready for reconciliation")
    else:
        st.error("Reconciliation not available")


def _render_reconciliation_controls() -> None:
    st.subheader("2. Configure reconciliation")
    reference_date = st.date_input(
        "Reference date (UTC)",
        value=date(2026, 3, 20),
    )
    reference_time = st.time_input(
        "Reference time (UTC)",
        value=time(12, 0),
        step=60,
    )
    tolerance = st.text_input("Monetary tolerance (EUR)", value="0.01")
    shipping_hours = st.number_input(
        "Shipping limit (whole hours)",
        min_value=1,
        value=48,
        step=1,
    )
    return_days = st.number_input(
        "Return-refund limit (whole days)",
        min_value=1,
        value=7,
        step=1,
    )
    high_hours = st.text_input(
        "High shipping delay threshold (whole hours, optional)",
        value="",
    )
    st.caption(
        f"Configuration shown in UTC: {reference_date.isoformat()} "
        f"{reference_time.isoformat(timespec='minutes')}; tolerance {tolerance} EUR; "
        f"shipping {shipping_hours} hours; return-refund {return_days} days."
    )
    validation = st.session_state.validation_result
    ready = validation is not None and validation.report.reconciliation_ready
    if st.button("Run reconciliation", disabled=not ready, type="primary"):
        try:
            config = build_reconciliation_config(
                tolerance,
                int(shipping_hours),
                int(return_days),
                high_hours,
            )
            st.session_state.reconciliation_result = reconcile_validation_result(
                validation,
                reference_date,
                reference_time,
                config,
            )
        except (TypeError, ValueError) as error:
            st.error(f"Reconciliation could not run: {error}")
        else:
            st.success("Reconciliation completed successfully.")


def _render_operational_summary() -> None:
    st.subheader("Operational summary")
    summary = operational_summary(
        st.session_state.validation_result,
        st.session_state.reconciliation_result,
    )
    first_row = st.columns(6)
    for column, label in zip(first_row, tuple(summary)[:6], strict=True):
        column.metric(label, summary[label])
    second_row = st.columns(3)
    for column, label in zip(second_row, tuple(summary)[6:], strict=True):
        column.metric(label, summary[label])


def _render_anomaly_dashboard() -> None:
    result = st.session_state.reconciliation_result
    st.subheader("3. Reconciliation results")
    if result is None:
        st.info("Anomalies are not calculated until reconciliation is run.")
        return

    anomalies = result.anomalies
    filters = st.columns(4)
    platforms = filters[0].multiselect(
        "Filter by platform",
        sorted({item.platform for item in anomalies}),
    )
    codes = filters[1].multiselect(
        "Filter by anomaly code",
        sorted({item.anomaly_code.value for item in anomalies}),
    )
    severities = filters[2].multiselect(
        "Filter by severity",
        sorted({item.severity.value for item in anomalies}),
    )
    statuses = filters[3].multiselect(
        "Filter by review status",
        sorted({item.review_status.value for item in anomalies}),
    )
    filtered = filter_anomalies(
        anomalies,
        platforms=platforms,
        anomaly_codes=codes,
        severities=severities,
        review_statuses=statuses,
    )
    st.caption(f"Showing {len(filtered)} of {len(anomalies)} anomalies.")
    if filtered:
        st.dataframe(
            anomaly_table_rows(filtered),
            hide_index=True,
            width="stretch",
        )
        selected_id = st.selectbox(
            "Select an anomaly to inspect",
            options=(None, *(item.anomaly_id for item in filtered)),
            format_func=lambda value: "Choose an anomaly" if value is None else value,
        )
        if selected_id is not None:
            selected = next(item for item in filtered if item.anomaly_id == selected_id)
            detail = anomaly_detail(selected)
            st.subheader("Anomaly detail")
            fields = {
                key: value
                for key, value in detail.items()
                if key not in {"Compared values", "Record references"}
            }
            st.table([fields])
            st.write("Compared values")
            st.json(dict(detail["Compared values"]))
            st.write("Source record references")
            st.dataframe(
                detail["Record references"],
                hide_index=True,
                width="stretch",
            )
    else:
        st.info("No anomalies match the selected filters.")

    st.subheader("Checks not evaluated")
    unavailable = not_evaluated_rows(result.not_evaluated)
    if unavailable:
        st.dataframe(unavailable, hide_index=True, width="stretch")
    else:
        st.info("All applicable reconciliation checks were evaluated.")


def render_app() -> None:
    """Render the user-facing upload foundation."""

    st.set_page_config(page_title=TITLE, page_icon="📦", layout="wide")
    _initialize_state()

    st.title(TITLE)
    st.caption(SUBTITLE)
    st.write(
        "Upload the five canonical CSV files to validate and reconcile one dataset. "
        "No terminal is needed after the application starts."
    )
    st.info(
        "Use only synthetic or explicitly authorized data. This MVP supports EUR only."
    )
    st.subheader("1. Upload dataset")
    st.write("Required files: " + ", ".join(f"`{name}`" for name in REQUIRED_FILENAMES))
    uploads = st.file_uploader(
        "Choose the five required CSV files",
        type=("csv",),
        accept_multiple_files=True,
        help="Upload exactly one orders, payments, shipments, returns, and refunds CSV.",
    )
    selection = inspect_uploads(uploads)
    if selection.missing:
        st.warning("Missing files: " + ", ".join(selection.missing))
    if selection.duplicates:
        st.error("Duplicate filenames: " + ", ".join(selection.duplicates))
    if selection.unexpected:
        st.error("Unexpected filenames: " + ", ".join(selection.unexpected))
    if uploads and selection.is_complete:
        st.success("All five required CSV files are ready for validation.")
        signature = upload_signature(uploads)
        if st.session_state.upload_signature != signature:
            st.session_state.upload_signature = signature
            st.session_state.validation_result = None
            st.session_state.reconciliation_result = None
        if st.button("Validate dataset"):
            try:
                st.session_state.validation_result = validate_uploads(uploads)
                st.session_state.reconciliation_result = None
            except (OSError, TypeError, ValueError) as error:
                st.error(f"Dataset validation could not run: {error}")

    _render_validation_report()
    _render_reconciliation_controls()
    _render_operational_summary()
    _render_anomaly_dashboard()


__all__ = ["SUBTITLE", "TITLE", "render_app"]
