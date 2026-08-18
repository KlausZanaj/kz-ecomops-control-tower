"""Repository-level guards against publishing runtime UI artifacts."""

from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]


def test_no_runtime_database_upload_cache_or_secret_is_tracked() -> None:
    completed = subprocess.run(
        (
            "git",
            "-c",
            f"safe.directory={PROJECT_ROOT.as_posix()}",
            "ls-files",
            "-z",
        ),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    tracked = tuple(
        Path(item)
        for item in completed.stdout.decode("utf-8").split("\0")
        if item
    )

    assert not any(".runtime" in path.parts for path in tracked)
    assert not any("upload" in part.lower() for path in tracked for part in path.parts[:-1])
    assert not any(path.suffix in {".db", ".sqlite", ".sqlite3", ".pyc"} for path in tracked)
    assert not any(path.name == ".env" or "__pycache__" in path.parts for path in tracked)
