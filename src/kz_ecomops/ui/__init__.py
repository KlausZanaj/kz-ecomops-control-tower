"""Testable presentation and workflow helpers for the Streamlit interface."""

from .uploads import (
    REQUIRED_FILENAMES,
    UploadSelection,
    UploadSelectionError,
    inspect_uploads,
    stage_uploads,
)
from .workflow import (
    build_reconciliation_config,
    reconcile_validation_result,
    upload_signature,
    validate_uploads,
)
from .presentation import (
    anomaly_detail,
    anomaly_table_rows,
    filter_anomalies,
    not_evaluated_rows,
    operational_summary,
)

__all__ = [
    "REQUIRED_FILENAMES",
    "UploadSelection",
    "UploadSelectionError",
    "inspect_uploads",
    "stage_uploads",
    "build_reconciliation_config",
    "reconcile_validation_result",
    "upload_signature",
    "validate_uploads",
    "anomaly_detail",
    "anomaly_table_rows",
    "filter_anomalies",
    "not_evaluated_rows",
    "operational_summary",
]
