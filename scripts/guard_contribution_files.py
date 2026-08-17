"""Local guard that ensures contribution work only touches entry files.

Allowed set: paths under data/contributions/entries/ (per the contribution
workflow plan, phase 02). It is a pre-push convenience check only: the GitHub
Actions review bot (phase 03) remains the authoritative gate.

Input: either --changed-files <path> [...], or newline-separated paths on
stdin (e.g. piped from "git diff --name-only"), or --git (runs
"git status --porcelain" in the project root as a fallback that also covers
untracked new files).

Exit code is 0 when every changed path is allowed, 1 otherwise.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_PREFIX = "data/contributions/entries/"


def classify_paths(changed_files: list[str]) -> tuple[list[str], list[str]]:
    """Split changed paths into (allowed, violations). Blank lines are ignored."""
    allowed: list[str] = []
    violations: list[str] = []
    for raw in changed_files:
        path = raw.strip()
        if not path:
            continue
        if path.startswith(ALLOWED_PREFIX):
            allowed.append(path)
        else:
            violations.append(path)
    return allowed, violations


def _git_changed_files() -> list[str]:
    """Fallback source: git status --porcelain (covers new/modified/deleted)."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError:
        return []
    if proc.returncode != 0:
        return []
    paths = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        paths.append(line[3:])
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本地护栏：只允许改动 data/contributions/entries/ 下的条目文件")
    parser.add_argument("--changed-files", nargs="*", help="变更文件路径列表")
    parser.add_argument(
        "--git",
        action="store_true",
        help="从 git status --porcelain 读取变更（覆盖新增/修改/删除与未跟踪文件）",
    )
    args = parser.parse_args(argv)

    if args.changed_files is not None:
        changed = list(args.changed_files)
    elif args.git:
        changed = _git_changed_files()
    elif not sys.stdin.isatty():
        changed = [line for line in sys.stdin.read().splitlines()]
    else:
        parser.error("请通过 --changed-files 提供路径，或通过管道输入 git diff 结果，或使用 --git")

    allowed, violations = classify_paths(changed)
    for path in allowed:
        print("[OK]   %s" % path)
    for path in violations:
        print("[FAIL] %s" % path)
    if violations:
        print(
            "护栏未通过：发现 %d 个越界文件。共创 PR 只允许新增 %s 下的条目文件。"
            % (len(violations), ALLOWED_PREFIX)
        )
        return 1
    print("护栏通过：变更仅涉及条目文件（%d 个）。" % len(allowed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
