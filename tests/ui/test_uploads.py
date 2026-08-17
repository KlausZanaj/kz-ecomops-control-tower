"""Tests for secure temporary Streamlit upload handling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from kz_ecomops.ui import (
    REQUIRED_FILENAMES,
    UploadSelectionError,
    inspect_uploads,
    stage_uploads,
)


@dataclass
class FakeUpload:
    name: str
    content: bytes = b"header\n"

    def getvalue(self) -> bytes:
        return self.content


def _complete_uploads() -> tuple[FakeUpload, ...]:
    return tuple(FakeUpload(filename) for filename in REQUIRED_FILENAMES)


def test_upload_selection_reports_missing_duplicate_and_unexpected_files() -> None:
    missing = inspect_uploads(_complete_uploads()[:-1])
    duplicate = inspect_uploads((*_complete_uploads(), FakeUpload("orders.csv")))
    unexpected = inspect_uploads((*_complete_uploads(), FakeUpload("future.csv")))

    assert missing.missing == ("refunds.csv",)
    assert duplicate.duplicates == ("orders.csv",)
    assert unexpected.unexpected == ("future.csv",)
    assert not missing.is_complete and not duplicate.is_complete and not unexpected.is_complete


def test_complete_uploads_exist_only_inside_temporary_context() -> None:
    uploads = tuple(
        FakeUpload(filename, f"{filename}-header\n".encode())
        for filename in REQUIRED_FILENAMES
    )

    with stage_uploads(uploads) as directory:
        staged_directory = directory
        assert {path.name for path in directory.iterdir()} == set(REQUIRED_FILENAMES)
        assert (directory / "orders.csv").read_bytes() == b"orders.csv-header\n"

    assert not staged_directory.exists()


def test_incomplete_selection_is_never_staged() -> None:
    with pytest.raises(UploadSelectionError, match="exactly one copy"):
        with stage_uploads(_complete_uploads()[:-1]):
            pytest.fail("Incomplete uploads must not produce a directory.")


def test_path_components_are_not_used_as_destination_paths() -> None:
    uploads = list(_complete_uploads())
    uploads[0] = FakeUpload("folder/orders.csv")

    with stage_uploads(uploads) as directory:
        assert (directory / "orders.csv").is_file()
        assert not (directory / "folder").exists()
