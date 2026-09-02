"""Audit the current repository and its Git history without exposing secrets.

The explicit allowlist is deliberately narrow:

* project author: Klaus Zanaj;
* GitHub private noreply address: 316658954+KlausZanaj@users.noreply.github.com;
* synthetic CSV files below data/sample (the contents are still secret-scanned);
* PNG screenshots below docs/assets.

Findings report only a category, path, optional commit, position and the literal
marker ``[REDACTED]``. Matched content is never returned or printed.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


AUTHOR_ALLOWLIST = frozenset({"Klaus Zanaj"})
EMAIL_ALLOWLIST = frozenset(
    {"316658954+KlausZanaj@users.noreply.github.com"}
)
SYNTHETIC_CSV_ROOT = PurePosixPath("data/sample")
SCREENSHOT_ROOT = PurePosixPath("docs/assets")
SCREENSHOT_EXTENSIONS = frozenset({".png"})
MAX_TRACKED_FILE_BYTES = 5 * 1024 * 1024
REDACTED = "[REDACTED]"

_DATABASE_EXTENSIONS = frozenset({".db", ".sqlite", ".sqlite3"})
_CACHE_PARTS = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)
_VENV_PARTS = frozenset({".venv", "venv", "env", "ENV"})
_TEMPORARY_EXTENSIONS = frozenset({".tmp", ".temp", ".bak", ".swp", ".swo"})
_UPLOAD_DIRECTORY_NAMES = frozenset({"upload", "uploads", "uploaded"})
_EXPECTED_TEXT_EXTENSIONS = frozenset(
    {
        "",
        ".cfg",
        ".csv",
        ".gitignore",
        ".ini",
        ".json",
        ".md",
        ".py",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
_TOKEN_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password|passwd)\b"
        r"\s*[:=]\s*['\"]?([A-Za-z0-9_./+=-]{12,})"
    ),
)
_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
_WINDOWS_USER_PATH = re.compile(
    r"(?i)\b[A-Z]:[\\/](?:Users|Documents and Settings)[\\/]"
    r"(?P<username>[^\\/\s'\"<>]+)"
)
_POSIX_USER_PATH = re.compile(
    r"/(?:home|Users)/(?P<username>[^/\s'\"<>]+)"
)
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_CARD_LIKE_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){15}\d(?!\d)")
_SAFE_SYNTHETIC_EMAIL_DOMAINS = frozenset(
    {"example.com", "example.org", "example.net", "example.invalid"}
)


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """One redacted repository policy violation."""

    category: str
    path: str
    position: str
    commit: str | None = None
    redacted: str = REDACTED


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Deterministic result of a repository audit."""

    repository: str
    scanned_current_files: int
    scanned_history_blobs: int
    scanned_commits: int
    findings: tuple[AuditFinding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings


class AuditExecutionError(RuntimeError):
    """Raised when the target is not a readable Git repository."""


def _git(repository: Path, *arguments: str) -> bytes:
    command = (
        "git",
        "-c",
        f"safe.directory={repository.as_posix()}",
        *arguments,
    )
    completed = subprocess.run(
        command,
        cwd=repository,
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise AuditExecutionError(
            f"Git command failed while auditing the repository: {message}"
        )
    return completed.stdout


def _normal_path(path: str) -> PurePosixPath:
    return PurePosixPath(path.replace("\\", "/"))


def _is_below(path: PurePosixPath, root: PurePosixPath) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _path_findings(path_text: str, size: int, commit: str | None) -> list[AuditFinding]:
    path = _normal_path(path_text)
    lower_parts = tuple(part.casefold() for part in path.parts)
    suffix = path.suffix.casefold()
    name = path.name.casefold()
    categories: list[str] = []

    if suffix in _DATABASE_EXTENSIONS:
        categories.append("database_artifact")
    if any(part in {value.casefold() for value in _VENV_PARTS} for part in lower_parts):
        categories.append("virtual_environment")
    if any(part in _CACHE_PARTS for part in lower_parts) or suffix in {".pyc", ".pyo"}:
        categories.append("cache_artifact")
    if suffix in _TEMPORARY_EXTENSIONS:
        categories.append("temporary_file")
    if name == ".env" or name.startswith(".env."):
        categories.append("environment_file")
    if suffix in {".pem", ".key"} or name in {"id_rsa", "id_ed25519"}:
        categories.append("private_key_file")
    if suffix == ".csv" and not _is_below(path, SYNTHETIC_CSV_ROOT):
        categories.append("csv_outside_synthetic_samples")
    if any(part in _UPLOAD_DIRECTORY_NAMES for part in lower_parts[:-1]):
        categories.append("upload_artifact")
    if (
        "benchmark" in name
        and suffix in {".csv", ".json", ".db", ".sqlite", ".sqlite3"}
    ):
        categories.append("benchmark_artifact")
    if size > MAX_TRACKED_FILE_BYTES:
        categories.append("unexpected_large_file")

    return [
        AuditFinding(
            category=category,
            path=path.as_posix(),
            position="path",
            commit=commit,
        )
        for category in categories
    ]


def _allowed_binary(path: PurePosixPath) -> bool:
    return _is_below(path, SCREENSHOT_ROOT) and path.suffix.casefold() in SCREENSHOT_EXTENSIONS


def _decode_text(path_text: str, content: bytes, commit: str | None) -> tuple[str | None, list[AuditFinding]]:
    path = _normal_path(path_text)
    if b"\x00" in content:
        if _allowed_binary(path):
            return None, []
        return None, [
            AuditFinding("unexpected_binary", path.as_posix(), "content", commit)
        ]
    try:
        return content.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        if _allowed_binary(path):
            return None, []
        category = (
            "unexpected_binary"
            if path.suffix.casefold() not in _EXPECTED_TEXT_EXTENSIONS
            else "non_utf8_tracked_file"
        )
        return None, [AuditFinding(category, path.as_posix(), "content", commit)]


def _content_findings(
    path_text: str,
    content: bytes,
    commit: str | None,
    local_usernames: frozenset[str],
) -> list[AuditFinding]:
    text, findings = _decode_text(path_text, content, commit)
    if text is None:
        return findings

    path = _normal_path(path_text)
    synthetic_sample = _is_below(path, SYNTHETIC_CSV_ROOT)
    for line_number, line in enumerate(text.splitlines(), start=1):
        position = f"line {line_number}"
        if _PRIVATE_KEY_PATTERN.search(line):
            findings.append(
                AuditFinding("private_key_material", path.as_posix(), position, commit)
            )
        if any(pattern.search(line) for pattern in _TOKEN_PATTERNS):
            findings.append(
                AuditFinding("credential_pattern", path.as_posix(), position, commit)
            )
        user_path_matches = (
            *_WINDOWS_USER_PATH.finditer(line),
            *_POSIX_USER_PATH.finditer(line),
        )
        if user_path_matches:
            findings.append(
                AuditFinding("absolute_local_path", path.as_posix(), position, commit)
            )
        path_usernames = {
            match.group("username").casefold() for match in user_path_matches
        }
        if path_usernames & local_usernames:
            findings.append(
                AuditFinding("local_username", path.as_posix(), position, commit)
            )
        if synthetic_sample:
            for match in _EMAIL_PATTERN.finditer(line):
                address = match.group(0)
                domain = address.rsplit("@", 1)[1].casefold()
                if address in EMAIL_ALLOWLIST or domain in _SAFE_SYNTHETIC_EMAIL_DOMAINS:
                    continue
                findings.append(
                    AuditFinding(
                        "apparently_real_sample_email",
                        path.as_posix(),
                        position,
                        commit,
                    )
                )
            if _CARD_LIKE_PATTERN.search(line):
                findings.append(
                    AuditFinding(
                        "card_like_sample_value",
                        path.as_posix(),
                        position,
                        commit,
                    )
                )
    return findings


def _current_files(repository: Path) -> list[tuple[str, bytes]]:
    names = _git(repository, "ls-files", "-z").decode("utf-8").split("\x00")
    files: list[tuple[str, bytes]] = []
    for name in names:
        if not name:
            continue
        files.append((name, (repository / Path(name)).read_bytes()))
    return files


def _history_blobs(repository: Path) -> tuple[list[tuple[str, bytes, str]], tuple[str, ...]]:
    commits = tuple(
        value
        for value in _git(repository, "rev-list", "--all")
        .decode("ascii")
        .splitlines()
        if value
    )
    blobs: list[tuple[str, bytes, str]] = []
    seen: set[tuple[str, str]] = set()
    for commit in commits:
        entries = _git(repository, "ls-tree", "-r", "-z", commit).split(b"\x00")
        for entry in entries:
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            _mode, object_type, object_id = metadata.decode("ascii").split()
            if object_type != "blob":
                continue
            path = raw_path.decode("utf-8")
            identity = (object_id, path)
            if identity in seen:
                continue
            seen.add(identity)
            blobs.append(
                (path, _git(repository, "cat-file", "blob", object_id), commit)
            )
    return blobs, commits


def _identity_findings(repository: Path, commits: Sequence[str]) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for commit in commits:
        identity = _git(
            repository,
            "show",
            "-s",
            "--format=%an%x00%ae",
            commit,
        ).decode("utf-8").rstrip("\n").split("\x00", 1)
        author, email = identity
        if author not in AUTHOR_ALLOWLIST:
            findings.append(
                AuditFinding("unapproved_git_author", "<commit-metadata>", "author", commit)
            )
        if email not in EMAIL_ALLOWLIST:
            findings.append(
                AuditFinding("unapproved_git_email", "<commit-metadata>", "email", commit)
            )
    return findings


def _deduplicate(findings: Iterable[AuditFinding]) -> tuple[AuditFinding, ...]:
    unique = {
        (finding.category, finding.path, finding.position, finding.commit): finding
        for finding in findings
    }
    return tuple(
        unique[key]
        for key in sorted(
            unique,
            key=lambda value: (value[0], value[1], value[2], value[3] or ""),
        )
    )


def audit_repository(
    repository: str | Path,
    *,
    include_history: bool = True,
    local_usernames: Iterable[str] | None = None,
) -> AuditReport:
    """Audit tracked files and, by default, every unique blob in Git history."""

    root = Path(repository).resolve()
    if not root.is_dir():
        raise AuditExecutionError("The audit target must be an existing directory.")
    _git(root, "rev-parse", "--git-dir")
    usernames = (
        frozenset(value.casefold() for value in local_usernames if value)
        if local_usernames is not None
        else frozenset({getpass.getuser().casefold()})
    )

    findings: list[AuditFinding] = []
    current = _current_files(root)
    for path, content in current:
        findings.extend(_path_findings(path, len(content), None))
        findings.extend(_content_findings(path, content, None, usernames))

    history: list[tuple[str, bytes, str]] = []
    commits: tuple[str, ...] = ()
    if include_history:
        history, commits = _history_blobs(root)
        for path, content, commit in history:
            findings.extend(_path_findings(path, len(content), commit))
            findings.extend(_content_findings(path, content, commit, usernames))
        findings.extend(_identity_findings(root, commits))

    return AuditReport(
        repository=".",
        scanned_current_files=len(current),
        scanned_history_blobs=len(history),
        scanned_commits=len(commits),
        findings=_deduplicate(findings),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit tracked files and Git history for unsafe artifacts."
    )
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument(
        "--current-only",
        action="store_true",
        help="Skip historical Git blobs and commit identities.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    return parser


def _json_report(report: AuditReport) -> str:
    payload = {
        "findings": [asdict(finding) for finding in report.findings],
        "passed": report.passed,
        "repository": report.repository,
        "scanned_commits": report.scanned_commits,
        "scanned_current_files": report.scanned_current_files,
        "scanned_history_blobs": report.scanned_history_blobs,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _text_report(report: AuditReport) -> str:
    lines = [
        "KZ EcomOps repository audit",
        f"Current tracked files: {report.scanned_current_files}",
        f"Historical blobs: {report.scanned_history_blobs}",
        f"Commits: {report.scanned_commits}",
        f"Verdict: {'PASS' if report.passed else 'FAIL'}",
    ]
    for finding in report.findings:
        commit = f" commit={finding.commit}" if finding.commit else ""
        lines.append(
            f"- {finding.category}: {finding.path} ({finding.position})"
            f"{commit} {finding.redacted}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = audit_repository(
            args.repository,
            include_history=not args.current_only,
        )
    except AuditExecutionError as exc:
        print(f"Audit could not run: {exc}", file=sys.stderr)
        return 2
    print(_json_report(report) if args.json else _text_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
