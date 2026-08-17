"""Safe structural reading of normalized UTF-8 CSV files."""

from __future__ import annotations

import csv
import stat
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pandas as pd

from .schemas import CsvSchema


class CsvReadErrorCode(StrEnum):
    """Stable codes for structural CSV reading errors."""

    FILE_NOT_FOUND = "file_not_found"
    NOT_A_FILE = "not_a_file"
    READ_ERROR = "read_error"
    INVALID_ENCODING = "invalid_encoding"
    EMPTY_FILE = "empty_file"
    MALFORMED_CSV = "malformed_csv"
    BLANK_COLUMN_NAME = "blank_column_name"
    DUPLICATE_COLUMNS = "duplicate_columns"
    MISSING_REQUIRED_COLUMNS = "missing_required_columns"


@dataclass(frozen=True, slots=True)
class CsvReadIssue:
    """Describe one structural problem found while reading a CSV file."""

    code: CsvReadErrorCode
    filename: str
    message: str
    columns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CsvReadResult:
    """Contain a loaded DataFrame or the structural issues that prevented it."""

    schema: CsvSchema
    dataframe: pd.DataFrame | None
    issues: tuple[CsvReadIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Return whether a DataFrame is available without structural issues."""

        return self.dataframe is not None and not self.issues

    @property
    def row_count(self) -> int:
        """Return the loaded row count, or zero when loading did not succeed."""

        return len(self.dataframe) if self.dataframe is not None else 0


def _single_issue_result(
    schema: CsvSchema,
    code: CsvReadErrorCode,
    filename: str,
    message: str,
) -> CsvReadResult:
    return CsvReadResult(
        schema=schema,
        dataframe=None,
        issues=(CsvReadIssue(code=code, filename=filename, message=message),),
    )


def _header_issues(
    header: list[str], schema: CsvSchema, filename: str
) -> tuple[CsvReadIssue, ...]:
    issues: list[CsvReadIssue] = []

    blank_columns = tuple(name for name in header if not name.strip())
    if blank_columns:
        blank_positions = tuple(
            str(position)
            for position, name in enumerate(header, start=1)
            if not name.strip()
        )
        issues.append(
            CsvReadIssue(
                code=CsvReadErrorCode.BLANK_COLUMN_NAME,
                filename=filename,
                message=(
                    f"CSV file {filename!r} has blank column names at position(s) "
                    f"{', '.join(blank_positions)}. Name every column in the header."
                ),
                columns=blank_columns,
            )
        )

    counts = Counter(header)
    duplicate_columns = tuple(
        name for name in dict.fromkeys(header) if counts[name] > 1
    )
    if duplicate_columns:
        issues.append(
            CsvReadIssue(
                code=CsvReadErrorCode.DUPLICATE_COLUMNS,
                filename=filename,
                message=(
                    f"CSV file {filename!r} has duplicate column name(s): "
                    f"{', '.join(repr(name) for name in duplicate_columns)}. "
                    "Use each column name only once."
                ),
                columns=duplicate_columns,
            )
        )

    available_columns = set(header)
    missing_columns = tuple(
        column.name
        for column in schema.required_columns
        if column.name not in available_columns
    )
    if missing_columns:
        issues.append(
            CsvReadIssue(
                code=CsvReadErrorCode.MISSING_REQUIRED_COLUMNS,
                filename=filename,
                message=(
                    f"CSV file {filename!r} is missing required column(s): "
                    f"{', '.join(missing_columns)}. Add them using the documented names."
                ),
                columns=missing_columns,
            )
        )

    return tuple(issues)


def read_csv_file(path: str | Path, schema: CsvSchema) -> CsvReadResult:
    """Read one normalized CSV after validating its header structure.

    The source file is opened as UTF-8, with optional BOM support, and is never
    modified. Values remain strings; value-level and cross-file validation are
    intentionally outside this function.
    """

    source_path = Path(path)
    filename = source_path.name or str(source_path)

    try:
        file_status = source_path.stat()
    except FileNotFoundError:
        return _single_issue_result(
            schema,
            CsvReadErrorCode.FILE_NOT_FOUND,
            filename,
            f"CSV file {filename!r} was not found. Check the file path.",
        )
    except OSError as error:
        return _single_issue_result(
            schema,
            CsvReadErrorCode.READ_ERROR,
            filename,
            (
                f"CSV file {filename!r} could not be inspected: {error}. "
                "Check the file permissions and availability."
            ),
        )

    if not stat.S_ISREG(file_status.st_mode):
        return _single_issue_result(
            schema,
            CsvReadErrorCode.NOT_A_FILE,
            filename,
            f"Path {str(source_path)!r} does not point to a file. Select a CSV file.",
        )

    if file_status.st_size == 0:
        return _single_issue_result(
            schema,
            CsvReadErrorCode.EMPTY_FILE,
            filename,
            f"CSV file {filename!r} is empty. Add the documented header row.",
        )

    try:
        with source_path.open(mode="r", encoding="utf-8-sig", newline="") as csv_file:
            rows = csv.reader(csv_file, delimiter=",", strict=True)
            try:
                header = next(rows)
            except StopIteration:
                return _single_issue_result(
                    schema,
                    CsvReadErrorCode.EMPTY_FILE,
                    filename,
                    f"CSV file {filename!r} is empty. Add the documented header row.",
                )

            issues = _header_issues(header, schema, filename)
            if issues:
                return CsvReadResult(schema=schema, dataframe=None, issues=issues)

            expected_field_count = len(header)
            for row in rows:
                if not row:
                    continue
                actual_field_count = len(row)
                if actual_field_count != expected_field_count:
                    return _single_issue_result(
                        schema,
                        CsvReadErrorCode.MALFORMED_CSV,
                        filename,
                        (
                            f"CSV file {filename!r} has a field-count mismatch at "
                            f"line {rows.line_num}: expected {expected_field_count} "
                            f"field(s) but found {actual_field_count}. Ensure every "
                            "non-empty record matches the header."
                        ),
                    )
    except UnicodeDecodeError:
        return _single_issue_result(
            schema,
            CsvReadErrorCode.INVALID_ENCODING,
            filename,
            (
                f"CSV file {filename!r} is not valid UTF-8. "
                "Save it with UTF-8 encoding and try again."
            ),
        )
    except csv.Error as error:
        return _single_issue_result(
            schema,
            CsvReadErrorCode.MALFORMED_CSV,
            filename,
            (
                f"CSV file {filename!r} is malformed: {error}. "
                "Fix the comma-separated fields and quoting."
            ),
        )
    except OSError as error:
        return _single_issue_result(
            schema,
            CsvReadErrorCode.READ_ERROR,
            filename,
            (
                f"CSV file {filename!r} could not be read: {error}. "
                "Check the file permissions and availability."
            ),
        )

    try:
        dataframe = pd.read_csv(
            source_path,
            encoding="utf-8-sig",
            sep=",",
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            on_bad_lines="error",
            index_col=False,
        )
    except pd.errors.EmptyDataError:
        return _single_issue_result(
            schema,
            CsvReadErrorCode.EMPTY_FILE,
            filename,
            f"CSV file {filename!r} is empty. Add the documented header row.",
        )
    except UnicodeDecodeError:
        return _single_issue_result(
            schema,
            CsvReadErrorCode.INVALID_ENCODING,
            filename,
            (
                f"CSV file {filename!r} is not valid UTF-8. "
                "Save it with UTF-8 encoding and try again."
            ),
        )
    except pd.errors.ParserError as error:
        return _single_issue_result(
            schema,
            CsvReadErrorCode.MALFORMED_CSV,
            filename,
            (
                f"CSV file {filename!r} is malformed: {error}. "
                "Fix the comma-separated fields and quoting."
            ),
        )
    except OSError as error:
        return _single_issue_result(
            schema,
            CsvReadErrorCode.READ_ERROR,
            filename,
            (
                f"CSV file {filename!r} could not be read: {error}. "
                "Check the file permissions and availability."
            ),
        )

    return CsvReadResult(schema=schema, dataframe=dataframe)
