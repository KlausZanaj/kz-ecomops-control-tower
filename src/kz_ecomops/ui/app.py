"""Streamlit application shell and upload foundation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timezone

import streamlit as st

from kz_ecomops.reconciliation import (
    ReconciliationAnomaly,
    ReconciliationResult,
    ReviewStatus,
)
from kz_ecomops.reporting import (
    AnomalyCsvExport,
    AnomalyDistributions,
    anomaly_distributions,
)
from kz_ecomops.validation import ValidationMessage, ValidationStage

from .uploads import REQUIRED_FILENAMES, inspect_uploads
from .presentation import (
    anomaly_detail,
    anomaly_table_rows,
    not_evaluated_rows,
    operational_summary,
    reconciliation_configuration,
)
from .reporting import build_filtered_anomaly_report
from .workflow import (
    build_reconciliation_config,
    reconciliation_input_signature,
    reconcile_validation_result,
    upload_signature,
    validate_uploads,
)
from .storage import (
    change_review_status,
    persist_and_refresh,
    runtime_database_path,
)


TITLE = "KZ EcomOps Control Tower"
SUBTITLE = "Multi-channel order reconciliation and e-commerce operations analytics."
_RESULT_WIDGET_KEYS = {
    "anomaly-code-filter",
    "anomaly-selection",
    "filtered-anomaly-download",
    "platform-filter",
    "review-status-filter",
    "severity-filter",
}


def _initialize_state() -> None:
    defaults = {
        "validation_result": None,
        "reconciliation_result": None,
        "current_upload_signature": None,
        "validated_upload_signature": None,
        "reconciliation_signature": None,
        "persistence_outcome": None,
        "review_notice": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _clear_result_widget_state() -> None:
    for key in tuple(st.session_state):
        if key in _RESULT_WIDGET_KEYS or key.startswith("review-status-"):
            del st.session_state[key]


def _invalidate_reconciliation_state() -> None:
    st.session_state.reconciliation_result = None
    st.session_state.reconciliation_signature = None
    st.session_state.persistence_outcome = None
    st.session_state.review_notice = None
    _clear_result_widget_state()


def _invalidate_upload_state() -> None:
    st.session_state.validation_result = None
    st.session_state.validated_upload_signature = None
    _invalidate_reconciliation_state()


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
        st.warning("Non-blocking relationship findings are evaluated by REC-10.")
        st.dataframe(
            _message_rows(relationships),
            hide_index=True,
            width="stretch",
        )
    if report.reconciliation_ready:
        st.success("Ready for reconciliation")
    else:
        st.error("Reconciliation not available")


def _render_reconciliation_controls(
    uploads_complete: bool,
    current_upload_signature: str,
) -> None:
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
    current_config = None
    current_reconciliation_signature = None
    try:
        current_config = build_reconciliation_config(
            tolerance,
            int(shipping_hours),
            int(return_days),
            high_hours,
        )
        current_reference_at = datetime.combine(
            reference_date,
            reference_time,
            tzinfo=timezone.utc,
        )
        current_reconciliation_signature = reconciliation_input_signature(
            current_reference_at,
            current_config,
        )
    except (TypeError, ValueError):
        pass

    if (
        st.session_state.reconciliation_result is not None
        and st.session_state.reconciliation_signature
        != current_reconciliation_signature
    ):
        _invalidate_reconciliation_state()

    validation = st.session_state.validation_result
    ready = (
        uploads_complete
        and validation is not None
        and validation.report.reconciliation_ready
        and st.session_state.validated_upload_signature
        == current_upload_signature
    )
    if st.button("Run reconciliation", disabled=not ready, type="primary"):
        try:
            if current_config is None:
                current_config = build_reconciliation_config(
                    tolerance,
                    int(shipping_hours),
                    int(return_days),
                    high_hours,
                )
            result = reconcile_validation_result(
                validation,
                reference_date,
                reference_time,
                current_config,
            )
            outcome = persist_and_refresh(
                runtime_database_path(),
                validation,
                result,
            )
            st.session_state.reconciliation_result = outcome.reconciliation_result
            st.session_state.persistence_outcome = outcome
            st.session_state.reconciliation_signature = reconciliation_input_signature(
                result.reference_at,
                result.config,
            )
        except (TypeError, ValueError) as error:
            st.error(f"Reconciliation could not run: {error}")
        else:
            st.success("Reconciliation completed and saved successfully.")


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


def _distribution_rows(
    distributions: AnomalyDistributions,
) -> list[dict[str, str | int]]:
    dimensions = (
        ("Anomaly code", distributions.by_anomaly_code),
        ("Severity", distributions.by_severity),
        ("Platform", distributions.by_platform),
        ("Review status", distributions.by_review_status),
    )
    return [
        {"Dimension": dimension, "Value": value, "Count": count}
        for dimension, values in dimensions
        for value, count in values.items()
    ]


def _render_anomaly_distributions(
    all_anomalies: Sequence[ReconciliationAnomaly],
    filtered_anomalies: Sequence[ReconciliationAnomaly],
) -> None:
    all_counts = anomaly_distributions(all_anomalies)
    filtered_counts = anomaly_distributions(filtered_anomalies)
    st.subheader("Operational anomaly distributions")
    all_metric, filtered_metric = st.columns(2)
    all_metric.metric("All anomalies", all_counts.total_count)
    filtered_metric.metric("Filtered anomalies", filtered_counts.total_count)
    st.caption(
        "Counts are shown for the complete result and for the current combined "
        "filters. Review-status counts use the latest saved status."
    )
    all_column, filtered_column = st.columns(2)
    with all_column:
        st.write("All anomaly distributions")
        all_rows = _distribution_rows(all_counts)
        if all_rows:
            st.dataframe(all_rows, hide_index=True, width="stretch")
        else:
            st.info("The current reconciliation contains zero anomalies.")
    with filtered_column:
        st.write("Filtered anomaly distributions")
        filtered_rows = _distribution_rows(filtered_counts)
        if filtered_rows:
            st.dataframe(filtered_rows, hide_index=True, width="stretch")
        else:
            st.info("The current filters match zero anomalies.")


def _render_filtered_export(
    result: ReconciliationResult,
    export: AnomalyCsvExport,
) -> None:
    st.subheader("Filtered CSV export")
    if export.row_count == 0:
        st.info(
            "The current filters match zero anomalies. The CSV will contain "
            "the header only."
        )
    st.write(f"Rows to export: **{export.row_count}**")
    st.write(f"Filename: `{export.filename}`")
    st.write(
        "Result reference UTC: "
        f"`{result.reference_at.astimezone(timezone.utc).isoformat()}`"
    )
    st.caption("The download contains only anomalies matching all current filters.")
    st.download_button(
        "Download filtered anomalies CSV",
        data=export.content,
        file_name=export.filename,
        mime="text/csv; charset=utf-8",
        key="filtered-anomaly-download",
        on_click="ignore",
    )


def _render_anomaly_dashboard() -> None:
    result = st.session_state.reconciliation_result
    st.subheader("3. Reconciliation results")
    if result is None:
        st.info("Anomalies are not calculated until reconciliation is run.")
        return

    st.write("Configuration used for this result")
    st.table([reconciliation_configuration(result)])

    anomalies = result.anomalies
    filters = st.columns(4)
    platforms = filters[0].multiselect(
        "Filter by platform",
        sorted({item.platform for item in anomalies}),
        key="platform-filter",
    )
    codes = filters[1].multiselect(
        "Filter by anomaly code",
        sorted({item.anomaly_code.value for item in anomalies}),
        key="anomaly-code-filter",
    )
    severities = filters[2].multiselect(
        "Filter by severity",
        sorted({item.severity.value for item in anomalies}),
        key="severity-filter",
    )
    statuses = filters[3].multiselect(
        "Filter by review status",
        sorted({item.review_status.value for item in anomalies}),
        key="review-status-filter",
    )
    reporting_view = build_filtered_anomaly_report(
        result,
        platforms=platforms,
        anomaly_codes=codes,
        severities=severities,
        review_statuses=statuses,
    )
    filtered = reporting_view.anomalies
    _render_anomaly_distributions(anomalies, filtered)
    st.caption(f"Showing {len(filtered)} of {len(anomalies)} anomalies.")
    _render_filtered_export(result, reporting_view.export)
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
            key="anomaly-selection",
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
            selected_status = st.selectbox(
                "Review status",
                options=tuple(status.value for status in ReviewStatus),
                index=tuple(ReviewStatus).index(selected.review_status),
                key=f"review-status-{selected.anomaly_id}",
            )
            if st.button(
                "Save review status",
                key=f"save-review-{selected.anomaly_id}",
            ):
                try:
                    st.session_state.reconciliation_result = change_review_status(
                        runtime_database_path(),
                        result,
                        selected.anomaly_id,
                        selected_status,
                    )
                except (OSError, TypeError, ValueError, KeyError) as error:
                    st.error(f"Review status could not be updated: {error}")
                else:
                    st.session_state.review_notice = (
                        f"Review status updated to {selected_status}."
                    )
                    st.rerun()
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
    if st.session_state.review_notice:
        st.success(st.session_state.review_notice)
        st.session_state.review_notice = None
    st.write(
        "Upload the five canonical CSV files to validate and reconcile one dataset. "
        "No terminal is needed after the application starts."
    )
    st.info(
        "Use only synthetic or explicitly authorized data. This MVP supports EUR only."
    )
    st.subheader("1. Upload dataset")
    st.write("Required files: " + ", ".join(f"`{name}`" for name in REQUIRED_FILENAMES))
    uploads = tuple(st.file_uploader(
        "Choose the five required CSV files",
        type=("csv",),
        accept_multiple_files=True,
        help="Upload exactly one orders, payments, shipments, returns, and refunds CSV.",
    ) or ())
    current_upload_signature = upload_signature(uploads)
    if st.session_state.current_upload_signature != current_upload_signature:
        _invalidate_upload_state()
        st.session_state.current_upload_signature = current_upload_signature
    selection = inspect_uploads(uploads)
    if selection.missing:
        st.warning("Missing files: " + ", ".join(selection.missing))
    if selection.duplicates:
        st.error("Duplicate filenames: " + ", ".join(selection.duplicates))
    if selection.unexpected:
        st.error("Unexpected filenames: " + ", ".join(selection.unexpected))
    if uploads and selection.is_complete:
        st.success("All five required CSV files are ready for validation.")
        if st.button("Validate dataset"):
            st.session_state.validation_result = None
            st.session_state.validated_upload_signature = None
            _invalidate_reconciliation_state()
            try:
                st.session_state.validation_result = validate_uploads(uploads)
            except (OSError, TypeError, ValueError) as error:
                st.error(f"Dataset validation could not run: {error}")
            else:
                st.session_state.validated_upload_signature = (
                    current_upload_signature
                )

    _render_validation_report()
    st.caption(
        "Local runtime database: "
        f"`{runtime_database_path().resolve()}`. Uploaded CSV files are not kept."
    )
    _render_reconciliation_controls(
        selection.is_complete,
        current_upload_signature,
    )
    _render_operational_summary()
    _render_anomaly_dashboard()


__all__ = ["SUBTITLE", "TITLE", "render_app"]
