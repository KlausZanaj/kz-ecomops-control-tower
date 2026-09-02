from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.audit_repository import REDACTED, audit_repository, main


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", "-c", f"safe.directory={repository.as_posix()}", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
    )


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "--local", "user.name", "Klaus Zanaj")
    _git(
        repository,
        "config",
        "--local",
        "user.email",
        "316658954+KlausZanaj@users.noreply.github.com",
    )
    (repository / "README.md").write_text("# Safe synthetic fixture\n", encoding="utf-8")
    sample = repository / "data" / "sample"
    sample.mkdir(parents=True)
    (sample / "orders.csv").write_text("order_id\nshopify:SYN-001\n", encoding="utf-8")
    _git(repository, "add", "--", ".")
    _git(repository, "commit", "-m", "test: safe fixture")
    return repository


def test_safe_synthetic_repository_passes_for_root_username(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    report = audit_repository(repository, local_usernames={"root"})

    assert report.passed
    assert report.scanned_current_files == 2
    assert report.scanned_commits == 1


def test_common_username_words_are_not_treated_as_local_identity(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    (repository / "README.md").write_text(
        "root application test runner are ordinary project words\n",
        encoding="utf-8",
    )

    for username in ("root", "app", "test", "user", "runner"):
        report = audit_repository(
            repository,
            include_history=False,
            local_usernames={username},
        )
        assert report.passed
        assert not any(
            finding.category == "local_username" for finding in report.findings
        )


def test_current_forbidden_files_and_values_are_redacted(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    secret = "ghp_" + "A" * 24
    local_path = "C:" + "/Users/" + "local-test-user/private.txt"
    (repository / ".env").write_text(
        f"ACCESS_TOKEN={secret}\nSOURCE={local_path}\n",
        encoding="utf-8",
    )
    (repository / "outside.csv").write_text("value\nsynthetic\n", encoding="utf-8")
    _git(repository, "add", "-f", "--", ".env", "outside.csv")

    report = audit_repository(
        repository,
        include_history=False,
        local_usernames={"local-test-user"},
    )

    categories = {finding.category for finding in report.findings}
    assert {
        "environment_file",
        "credential_pattern",
        "absolute_local_path",
        "local_username",
        "csv_outside_synthetic_samples",
    } <= categories
    assert secret not in repr(report)
    assert local_path not in repr(report)
    assert all(finding.redacted == REDACTED for finding in report.findings)


def test_windows_and_posix_user_paths_are_detected_and_redacted(
    tmp_path: Path,
    capsys,
) -> None:
    repository = _repository(tmp_path)
    username = "local-test-user"
    windows_path = "C:" + "\\Users\\" + username + "\\private.txt"
    posix_path = "/" + "home/" + username + "/private.txt"
    (repository / "paths.txt").write_text(
        f"WINDOWS={windows_path}\nPOSIX={posix_path}\n",
        encoding="utf-8",
    )
    _git(repository, "add", "--", "paths.txt")

    report = audit_repository(
        repository,
        include_history=False,
        local_usernames={username},
    )

    assert [
        finding.category
        for finding in report.findings
        if finding.category == "absolute_local_path"
    ] == ["absolute_local_path", "absolute_local_path"]
    assert [
        finding.category
        for finding in report.findings
        if finding.category == "local_username"
    ] == ["local_username", "local_username"]
    assert username not in repr(report)
    assert windows_path not in repr(report)
    assert posix_path not in repr(report)

    exit_code = main(
        ["--repository", str(repository), "--current-only", "--json"]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "absolute_local_path" in output
    assert REDACTED in output
    assert username not in output
    assert windows_path not in output
    assert posix_path not in output


def test_deleted_secret_is_detected_in_history(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    private_key = "-----BEGIN " + "PRIVATE KEY-----\nsynthetic-test-material\n"
    key_file = repository / "temporary.pem"
    key_file.write_text(private_key, encoding="utf-8")
    _git(repository, "add", "--", "temporary.pem")
    _git(repository, "commit", "-m", "test: add forbidden fixture")
    key_file.unlink()
    _git(repository, "add", "--", "temporary.pem")
    _git(repository, "commit", "-m", "test: remove forbidden fixture")

    current = audit_repository(
        repository,
        include_history=False,
        local_usernames={"local-test-user"},
    )
    historical = audit_repository(
        repository,
        include_history=True,
        local_usernames={"local-test-user"},
    )

    assert current.passed
    assert {finding.category for finding in historical.findings} >= {
        "private_key_file",
        "private_key_material",
    }
    assert all(finding.commit for finding in historical.findings)
    assert private_key not in repr(historical)


def test_cli_returns_nonzero_without_revealing_secret(
    tmp_path: Path,
    capsys,
) -> None:
    repository = _repository(tmp_path)
    secret = "sk-" + "B" * 24
    (repository / "unsafe.txt").write_text(secret, encoding="utf-8")
    _git(repository, "add", "--", "unsafe.txt")

    exit_code = main(
        ["--repository", str(repository), "--current-only", "--json"]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "credential_pattern" in output
    assert REDACTED in output
    assert secret not in output


def test_cli_passes_when_default_username_is_root(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    repository = _repository(tmp_path)
    monkeypatch.setattr("scripts.audit_repository.getpass.getuser", lambda: "root")

    exit_code = main(
        ["--repository", str(repository), "--current-only", "--json"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"passed": true' in output
    assert "local_username" not in output


def test_current_repository_passes_for_root_username() -> None:
    repository = Path(__file__).parents[2]

    report = audit_repository(repository, local_usernames={"root"})

    assert report.passed
    assert report.findings == ()
