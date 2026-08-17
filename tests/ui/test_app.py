"""Streamlit AppTest coverage for the application shell."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).parents[2]


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
