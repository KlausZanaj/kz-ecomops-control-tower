"""Streamlit application shell and upload foundation."""

from __future__ import annotations

import streamlit as st

from .uploads import REQUIRED_FILENAMES, inspect_uploads


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


__all__ = ["SUBTITLE", "TITLE", "render_app"]
