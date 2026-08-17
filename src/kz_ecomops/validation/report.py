"""Uniform immutable reports for complete dataset validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

import pandas as pd

from .schemas import CSV_SCHEMAS


class ValidationStage(StrEnum):
    """Ordered stages in the normalized CSV validation pipeline."""

    READ = "read"
    VALUE = "value"
    INTEGRITY = "integrity"
    UNIQUENESS = "uniqueness"
    RELATIONSHIP = "relationship"


@dataclass(frozen=True, slots=True)
class ValidationMessage:
    """Represent one uniform validation error or non-blocking finding."""

    stage: ValidationStage
    code: str
    filename: str
    row_numbers: tuple[int, ...]
    columns: tuple[str, ...]
    message: str
    blocking: bool


@dataclass(frozen=True, slots=True)
class FileValidationReport:
    """Summarize validation outcomes and row counts for one required CSV file."""

    filename: str
    row_count: int
    accepted_row_count: int
    rejected_row_count: int
    messages: tuple[ValidationMessage, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Return whether this file has no blocking messages."""

        return not any(message.blocking for message in self.messages)

    @property
    def blocking_message_count(self) -> int:
        """Return the number of blocking validation messages."""

        return sum(message.blocking for message in self.messages)

    @property
    def relationship_finding_count(self) -> int:
        """Return the number of non-blocking relationship findings."""

        return sum(
            message.stage is ValidationStage.RELATIONSHIP
            for message in self.messages
        )


@dataclass(frozen=True, slots=True)
class DatasetValidationReport:
    """Aggregate deterministic validation reports for the required dataset."""

    files: tuple[FileValidationReport, ...]

    def get_file(self, filename: str) -> FileValidationReport:
        """Return one file report or raise a descriptive error."""

        for file_report in self.files:
            if file_report.filename == filename:
                return file_report
        raise KeyError(f"No validation report exists for CSV file {filename!r}.")

    @property
    def messages(self) -> tuple[ValidationMessage, ...]:
        """Return all messages in deterministic file and stage order."""

        return tuple(
            message
            for file_report in self.files
            for message in file_report.messages
        )

    @property
    def total_row_count(self) -> int:
        """Return the total number of structurally readable records."""

        return sum(file_report.row_count for file_report in self.files)

    @property
    def accepted_row_count(self) -> int:
        """Return the total number of rows without blocking row-level errors."""

        return sum(file_report.accepted_row_count for file_report in self.files)

    @property
    def rejected_row_count(self) -> int:
        """Return the total number of rows with blocking row-level errors."""

        return sum(file_report.rejected_row_count for file_report in self.files)

    @property
    def blocking_message_count(self) -> int:
        """Return the total number of blocking validation messages."""

        return sum(
            file_report.blocking_message_count for file_report in self.files
        )

    @property
    def relationship_finding_count(self) -> int:
        """Return the total number of non-blocking relationship findings."""

        return sum(
            file_report.relationship_finding_count for file_report in self.files
        )

    @property
    def is_valid(self) -> bool:
        """Return whether every included file report has no blocking messages."""

        return all(file_report.is_valid for file_report in self.files)

    @property
    def reconciliation_ready(self) -> bool:
        """Return whether all required files passed every blocking validation."""

        expected_filenames = set(CSV_SCHEMAS)
        reported_filenames = {file_report.filename for file_report in self.files}
        return (
            len(self.files) == len(expected_filenames)
            and reported_filenames == expected_filenames
            and self.is_valid
        )


@dataclass(frozen=True, slots=True)
class DatasetValidationResult:
    """Return a complete report and, when safe, a protected DataFrame mapping."""

    report: DatasetValidationReport
    dataframes: Mapping[str, pd.DataFrame] | None

    def __post_init__(self) -> None:
        if self.dataframes is not None:
            object.__setattr__(
                self,
                "dataframes",
                MappingProxyType(dict(self.dataframes)),
            )
