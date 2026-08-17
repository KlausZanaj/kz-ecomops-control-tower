"""Tests for safe structural reading of normalized CSV files."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pandas as pd
import pytest

from kz_ecomops.validation import (
    ColumnSchema,
    CsvReadErrorCode,
    CsvReadIssue,
    CsvReadResult,
    CsvSchema,
    DataType,
    read_csv_file,
)


TEST_SCHEMA = CsvSchema(
    filename="records.csv",
    columns=(
        ColumnSchema("record_id", DataType.STRING, True),
        ColumnSchema("status", DataType.STRING, True),
        ColumnSchema("note", DataType.STRING, False),
    ),
)


def _write_csv(tmp_path: Path, content: str, *, name: str = "records.csv") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8", newline="")
    return path


def _only_issue(result: CsvReadResult) -> CsvReadIssue:
    assert result.dataframe is None
    assert len(result.issues) == 1
    return result.issues[0]


def test_reads_minimal_valid_csv(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status\n001,open\n")

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.is_valid
    assert result.issues == ()
    assert result.dataframe is not None
    assert result.dataframe.to_dict(orient="records") == [
        {"record_id": "001", "status": "open"}
    ]


@pytest.mark.parametrize("as_string", [False, True])
def test_accepts_path_and_string_inputs(tmp_path: Path, as_string: bool) -> None:
    path = _write_csv(tmp_path, "record_id,status\n001,open\n")
    input_path: str | Path = str(path) if as_string else path

    result = read_csv_file(input_path, TEST_SCHEMA)

    assert result.is_valid
    assert result.row_count == 1


def test_preserves_leading_zeroes_in_identifiers(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status\n00017,open\n")

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.dataframe is not None
    assert result.dataframe.at[0, "record_id"] == "00017"


def test_keeps_all_values_as_strings(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status,note\n7,42,3.50\n")

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.dataframe is not None
    assert all(
        isinstance(value, str)
        for value in result.dataframe.iloc[0].tolist()
    )
    assert result.dataframe.iloc[0].tolist() == ["7", "42", "3.50"]


def test_keeps_empty_fields_as_empty_strings(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status,note\n1,open,\n")

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.dataframe is not None
    assert result.dataframe.at[0, "note"] == ""
    assert not pd.isna(result.dataframe.at[0, "note"])


def test_accepts_valid_header_with_zero_rows(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status,note\n")

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.is_valid
    assert result.row_count == 0
    assert result.dataframe is not None
    assert list(result.dataframe.columns) == ["record_id", "status", "note"]


def test_accepts_missing_optional_columns(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status\n1,open\n")

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.is_valid
    assert result.dataframe is not None
    assert list(result.dataframe.columns) == ["record_id", "status"]


def test_accepts_and_preserves_additional_columns(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,extra,status\n1,value,open\n")

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.is_valid
    assert result.dataframe is not None
    assert list(result.dataframe.columns) == ["record_id", "extra", "status"]
    assert result.dataframe.at[0, "extra"] == "value"


def test_reports_missing_required_column(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,note\n1,text\n")

    issue = _only_issue(read_csv_file(path, TEST_SCHEMA))

    assert issue.code is CsvReadErrorCode.MISSING_REQUIRED_COLUMNS
    assert issue.filename == "records.csv"
    assert issue.columns == ("status",)
    assert "status" in issue.message


def test_reports_multiple_missing_columns_in_schema_order(tmp_path: Path) -> None:
    schema = CsvSchema(
        filename="ordered.csv",
        columns=(
            ColumnSchema("third", DataType.STRING, True),
            ColumnSchema("first", DataType.STRING, False),
            ColumnSchema("second", DataType.STRING, True),
        ),
    )
    path = _write_csv(tmp_path, "extra\nvalue\n", name="ordered.csv")

    issue = _only_issue(read_csv_file(path, schema))

    assert issue.code is CsvReadErrorCode.MISSING_REQUIRED_COLUMNS
    assert issue.columns == ("third", "second")


def test_reports_duplicate_headers_before_pandas_can_rename_them(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status,status\n1,open,closed\n")

    issue = _only_issue(read_csv_file(path, TEST_SCHEMA))

    assert issue.code is CsvReadErrorCode.DUPLICATE_COLUMNS
    assert issue.columns == ("status",)
    assert "duplicate" in issue.message.lower()


@pytest.mark.parametrize("blank_name", ["", "   "])
def test_reports_blank_or_whitespace_only_column_name(
    tmp_path: Path, blank_name: str
) -> None:
    path = _write_csv(tmp_path, f"record_id,status,{blank_name}\n1,open,value\n")

    issue = _only_issue(read_csv_file(path, TEST_SCHEMA))

    assert issue.code is CsvReadErrorCode.BLANK_COLUMN_NAME
    assert issue.columns == (blank_name,)
    assert "position(s) 3" in issue.message


def test_reports_completely_empty_file(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "")

    issue = _only_issue(read_csv_file(path, TEST_SCHEMA))

    assert issue.code is CsvReadErrorCode.EMPTY_FILE
    assert "header" in issue.message


def test_reports_invalid_utf8_encoding(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    path.write_bytes(b"record_id,status\n1,\xff\n")

    issue = _only_issue(read_csv_file(path, TEST_SCHEMA))

    assert issue.code is CsvReadErrorCode.INVALID_ENCODING
    assert "UTF-8" in issue.message


def test_reports_malformed_csv(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, 'record_id,status\n1,"open\n')

    issue = _only_issue(read_csv_file(path, TEST_SCHEMA))

    assert issue.code is CsvReadErrorCode.MALFORMED_CSV
    assert "malformed" in issue.message


def test_reports_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"

    issue = _only_issue(read_csv_file(path, TEST_SCHEMA))

    assert issue.code is CsvReadErrorCode.FILE_NOT_FOUND
    assert issue.filename == "missing.csv"
    assert "not found" in issue.message


def test_reports_directory_instead_of_file(tmp_path: Path) -> None:
    issue = _only_issue(read_csv_file(tmp_path, TEST_SCHEMA))

    assert issue.code is CsvReadErrorCode.NOT_A_FILE
    assert "does not point to a file" in issue.message


def test_reports_operating_system_inspection_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "records.csv"

    def raise_os_error(_path: Path) -> None:
        raise OSError("access denied")

    monkeypatch.setattr(Path, "stat", raise_os_error)

    issue = _only_issue(read_csv_file(path, TEST_SCHEMA))

    assert issue.code is CsvReadErrorCode.READ_ERROR
    assert "access denied" in issue.message


@pytest.mark.parametrize(
    "content",
    [
        "record_id\n1\n",
        "record_id,status,status\n1,open,closed\n",
        "record_id,status, \n1,open,value\n",
    ],
)
def test_invalid_structure_never_returns_dataframe(
    tmp_path: Path, content: str
) -> None:
    path = _write_csv(tmp_path, content)

    result = read_csv_file(path, TEST_SCHEMA)

    assert not result.is_valid
    assert result.dataframe is None
    assert result.issues


def test_is_valid_and_row_count_for_valid_result(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status\n1,open\n2,closed\n")

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.is_valid is True
    assert result.row_count == 2


def test_is_valid_and_row_count_for_invalid_result(tmp_path: Path) -> None:
    result = read_csv_file(tmp_path / "missing.csv", TEST_SCHEMA)

    assert result.is_valid is False
    assert result.row_count == 0


def test_csv_read_issue_is_frozen_and_slotted() -> None:
    issue = CsvReadIssue(
        code=CsvReadErrorCode.EMPTY_FILE,
        filename="records.csv",
        message="The file is empty.",
    )

    with pytest.raises(FrozenInstanceError):
        issue.filename = "changed.csv"  # type: ignore[misc]
    assert not hasattr(issue, "__dict__")


def test_csv_read_result_is_frozen_and_slotted() -> None:
    result = CsvReadResult(schema=TEST_SCHEMA, dataframe=pd.DataFrame())

    with pytest.raises(FrozenInstanceError):
        result.schema = TEST_SCHEMA  # type: ignore[misc]
    assert not hasattr(result, "__dict__")


def test_csv_read_error_code_values_are_exact() -> None:
    assert {code.value for code in CsvReadErrorCode} == {
        "file_not_found",
        "not_a_file",
        "read_error",
        "invalid_encoding",
        "empty_file",
        "malformed_csv",
        "blank_column_name",
        "duplicate_columns",
        "missing_required_columns",
    }


def test_reading_does_not_modify_original_file(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status,note\n001,open,hello\n")
    original = path.read_bytes()

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.is_valid
    assert path.read_bytes() == original


def test_utf8_bom_does_not_contaminate_first_column_name(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    path.write_bytes(b"\xef\xbb\xbfrecord_id,status\n001,open\n")

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.is_valid
    assert result.dataframe is not None
    assert list(result.dataframe.columns) == ["record_id", "status"]
    assert result.dataframe.at[0, "record_id"] == "001"


def test_reports_record_with_fewer_fields_than_header(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status,note\n1,open\n")

    result = read_csv_file(path, TEST_SCHEMA)
    issue = _only_issue(result)

    assert issue.code is CsvReadErrorCode.MALFORMED_CSV
    assert result.dataframe is None
    assert "line 2" in issue.message
    assert "expected 3 field(s) but found 2" in issue.message


def test_reports_record_with_more_fields_than_header(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status\n1,open,unexpected\n")

    result = read_csv_file(path, TEST_SCHEMA)
    issue = _only_issue(result)

    assert issue.code is CsvReadErrorCode.MALFORMED_CSV
    assert result.dataframe is None
    assert "expected 2 field(s) but found 3" in issue.message


def test_preserves_quoted_field_containing_comma(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, 'record_id,status,note\n1,open,"hello, world"\n')

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.is_valid
    assert result.dataframe is not None
    assert result.dataframe.at[0, "note"] == "hello, world"


def test_preserves_quoted_field_containing_newline(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path,
        'record_id,status,note\n1,open,"first line\nsecond line"\n',
    )

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.is_valid
    assert result.row_count == 1
    assert result.dataframe is not None
    assert result.dataframe.at[0, "note"] == "first line\nsecond line"


def test_ignores_physical_blank_line_between_records(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "record_id,status\n1,open\n\n2,closed\n")

    result = read_csv_file(path, TEST_SCHEMA)

    assert result.is_valid
    assert result.row_count == 2
    assert result.dataframe is not None
    assert result.dataframe["record_id"].tolist() == ["1", "2"]
