"""Tests for scripts/guard_contribution_files.py (phase 02 local guard)."""

import subprocess
import sys
from pathlib import Path

from scripts.guard_contribution_files import ALLOWED_PREFIX, PROJECT_ROOT, classify_paths, main


def test_new_entry_file_is_allowed():
    allowed, violations = classify_paths(
        ["data/contributions/entries/game/black-myth-wukong--foguang-temple.csv"]
    )
    assert allowed == ["data/contributions/entries/game/black-myth-wukong--foguang-temple.csv"]
    assert violations == []


def test_entry_files_in_any_ip_type_dir_are_allowed():
    allowed, violations = classify_paths(
        [
            "data/contributions/entries/literature/luxun--baicaoyuan.csv",
            "data/contributions/entries/screen/jiufen--old-street.csv",
        ]
    )
    assert len(allowed) == 2
    assert violations == []


def test_app_file_is_violation():
    allowed, violations = classify_paths(["app/main.py"])
    assert allowed == []
    assert violations == ["app/main.py"]


def test_seed_and_tests_and_github_are_violations():
    allowed, violations = classify_paths(
        [
            "data/seed/landmarks_verified.csv",
            "tests/web/test_contributors.py",
            ".github/workflows/review-contribution.yml",
            "data/contributions/contributors.json",
        ]
    )
    assert allowed == []
    assert len(violations) == 4


def test_blank_lines_are_ignored():
    allowed, violations = classify_paths(["", "   ", "data/contributions/entries/game/a--b.csv", ""])
    assert len(allowed) == 1
    assert violations == []


def test_mixed_paths_split_correctly():
    allowed, violations = classify_paths(
        [
            "data/contributions/entries/game/a--b.csv",
            "app/services/import_landmarks.py",
            "data/contributions/entries/literature/c--d.csv",
            "README.md",
        ]
    )
    assert allowed == [
        "data/contributions/entries/game/a--b.csv",
        "data/contributions/entries/literature/c--d.csv",
    ]
    assert violations == ["app/services/import_landmarks.py", "README.md"]


def test_allowed_prefix_constant_points_at_entries_dir():
    assert ALLOWED_PREFIX == "data/contributions/entries/"


def test_cli_accepts_changed_files_args(capsys):
    exit_code = main(
        [
            "--changed-files",
            "data/contributions/entries/game/a--b.csv",
            "data/contributions/entries/game/c--d.csv",
        ]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "护栏通过" in out


def test_cli_rejects_violations(capsys):
    exit_code = main(["--changed-files", "data/contributions/entries/game/a--b.csv", "app/main.py"])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "越界" in out
    assert "app/main.py" in out


def test_cli_reads_piped_stdin(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr(
        "sys.stdin.read", lambda: "data/contributions/entries/game/a--b.csv\nREADME.md\n"
    )
    exit_code = main([])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "README.md" in out


def test_git_fallback_uses_repo_cwd(capsys, monkeypatch):
    captured = {}

    def fake_run(cmd, cwd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        import subprocess as _sp

        class Proc:
            returncode = 0
            stdout = " M app/main.py\n?? data/contributions/entries/game/a--b.csv\n"

        return Proc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    exit_code = main(["--git"])
    assert exit_code == 1
    assert captured["cwd"] == PROJECT_ROOT
    assert "app/main.py" in capsys.readouterr().out
