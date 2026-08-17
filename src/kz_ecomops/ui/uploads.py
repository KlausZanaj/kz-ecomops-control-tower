"""Secure, temporary handling for the five required uploaded CSV files."""

from __future__ import annotations

import tempfile
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kz_ecomops.validation import CSV_SCHEMAS


REQUIRED_FILENAMES = tuple(CSV_SCHEMAS)


class UploadedCsv(Protocol):
    """Minimal interface shared by Streamlit uploads and test doubles."""

    name: str

    def getvalue(self) -> bytes:
        """Return the uploaded file bytes."""


@dataclass(frozen=True, slots=True)
class UploadSelection:
    """Describe whether one upload selection is safe and complete."""

    missing: tuple[str, ...] = ()
    duplicates: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        return not (self.missing or self.duplicates or self.unexpected)


class UploadSelectionError(ValueError):
    """Reject an incomplete or ambiguous upload selection."""


def _safe_name(upload: UploadedCsv) -> str:
    return Path(upload.name.replace("\\", "/")).name


def inspect_uploads(uploads: Iterable[UploadedCsv]) -> UploadSelection:
    """Check exact filenames without reading or persisting uploaded contents."""

    names = tuple(_safe_name(upload) for upload in uploads)
    counts = Counter(names)
    required = set(REQUIRED_FILENAMES)
    return UploadSelection(
        missing=tuple(filename for filename in REQUIRED_FILENAMES if filename not in counts),
        duplicates=tuple(sorted(name for name, count in counts.items() if count > 1)),
        unexpected=tuple(sorted(name for name in counts if name not in required)),
    )


@contextmanager
def stage_uploads(uploads: Iterable[UploadedCsv]) -> Iterator[Path]:
    """Write complete uploads to an automatically deleted temporary directory."""

    upload_items = tuple(uploads)
    selection = inspect_uploads(upload_items)
    if not selection.is_complete:
        raise UploadSelectionError(
            "Upload exactly one copy of each required CSV file before continuing."
        )
    with tempfile.TemporaryDirectory(prefix="kz-ecomops-upload-") as temporary:
        directory = Path(temporary)
        for upload in upload_items:
            (directory / _safe_name(upload)).write_bytes(upload.getvalue())
        yield directory
