"""Pure review logic shared by the GitHub Actions review bot (phase 03).

The review bot performs two deterministic checks on a contribution PR:

1. File lockdown: only newly added files under data/contributions/entries/
   are allowed (relative paths as reported by git diff --name-only, or
   absolute paths for local testing).
2. Entry validation: every added entry file is validated with the phase 01
   validator (scripts/validate_contribution_entry.py).

This module keeps the pure logic (classification, comment rendering) separate
from the GitHub Actions glue so it can be covered by pytest locally without
running a real workflow.

CLI (used by the workflow):

    python3 scripts/review_logic.py classify --changed-file-list <path> --json
    python3 scripts/review_logic.py review --changed-file-list <path> --author <login> --json

classify has no third-party dependency and is used by the path-gate job
before dependencies are installed. review additionally validates the
allowed entry files (requires the project virtualenv / installed deps).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.guard_contribution_files import ALLOWED_PREFIX  # noqa: E402

PROMPT_PACK_PATH = "docs/共创提示词包/00_使用说明.md"
DEFAULT_ENTRIES_DIR = PROJECT_ROOT / "data" / "contributions" / "entries"
DEFAULT_SEED_PATH = PROJECT_ROOT / "data" / "seed" / "landmarks_verified.csv"


def classify_changed_files(
    changed_files: list[str], entries_dir: Path = DEFAULT_ENTRIES_DIR
) -> tuple[list[str], list[str]]:
    """Split changed paths into (allowed, violations). Blank lines are ignored.

    A path is allowed when it starts with the relative entries prefix (the
    format produced by git diff --name-only) or when it resolves inside
    entries_dir (used by local tests with temporary directories).
    """
    allowed: list[str] = []
    violations: list[str] = []
    root = entries_dir.resolve()
    for raw in changed_files:
        path = raw.strip()
        if not path:
            continue
        candidate = Path(path)
        if path.startswith(ALLOWED_PREFIX):
            allowed.append(path)
        elif candidate.is_absolute() and root in candidate.resolve().parents:
            allowed.append(path)
        else:
            violations.append(path)
    return allowed, violations


def _display_path(file_path: str, entries_dir: Path = DEFAULT_ENTRIES_DIR) -> str:
    """Show a review file path relative to the entries directory when possible."""
    try:
        return Path(file_path).resolve().relative_to(entries_dir.resolve()).as_posix()
    except ValueError:
        return Path(file_path).name


def _code_span(text: str) -> str:
    """Wrap text in a single pair of backticks (GitHub markdown code span)."""
    return "`" + text + "`"


def build_review_comment(review: dict) -> str:
    """Render the fixed-format review comment from a review payload dict."""
    author = review.get("author") or "unknown"
    violations = review.get("violations") or []
    results = review.get("validation_results") or []
    source_check = review.get("source_check", "disabled")
    entries_dir = Path(review.get("entries_dir") or DEFAULT_ENTRIES_DIR)

    lines = ["## 共创条目审核结果", f"- PR 作者：@{author}"]
    if violations:
        lines.append(f"- 越界文件检查：❌ 发现 {len(violations)} 个越界文件（仅允许新增条目文件）")
        for path in violations:
            lines.append(f"  - " + _code_span(path))
    else:
        lines.append("- 越界文件检查：✅ 仅新增条目文件")

    if not violations:
        invalid = [result for result in results if not result["valid"]]
        if invalid:
            lines.append(f"- 条目校验：❌ {len(invalid)} 个文件未通过")
            for result in invalid:
                detail = "；".join(result["errors"]) or "校验失败"
                lines.append(f"  - " + _code_span(_display_path(result["file"], entries_dir)) + f"：{detail}")
        elif results:
            lines.append(f"- 条目校验：✅ {len(results)} 个文件全部通过")
        else:
            lines.append("- 条目校验：⚠️ 未发现条目文件")

        duplicates = [
            result
            for result in results
            if not result.get("summary", {}).get("checks", {}).get("duplicate", True)
        ]
        lines.append("- 重复检查：" + ("❌ 与既有数据重复" if duplicates else "✅ 无重复"))

        if source_check == "enabled":
            warnings = [warning for result in results for warning in result.get("warnings", [])]
            lines.append("- 来源可达性：⚠️ 已启用，仅提醒不阻塞")
            for warning in warnings:
                lines.append(f"  - {warning}")
        else:
            lines.append("- 来源可达性：⚠️ 未启用（可选）")

    if not violations and results and not invalid:
        lines.append("")
        lines.append("校验通过，等待维护者人工确认。")

    lines.append("")
    lines.append(f"请按 " + _code_span(PROMPT_PACK_PATH) + " 修复后推送更新，机器人会自动复查。")
    return "\n".join(lines)


def build_review_payload(
    changed_files: list[str],
    author: str,
    seed_csv_path: Path = DEFAULT_SEED_PATH,
    entries_dir: Path = DEFAULT_ENTRIES_DIR,
    check_source: bool = False,
) -> dict:
    """Classify changed files, validate allowed entries, and render the comment."""
    from scripts.validate_contribution_entry import validate_entry_file  # lazy: needs deps

    allowed, violations = classify_changed_files(changed_files, entries_dir=entries_dir)
    validation_results: list[dict] = []
    for path in allowed:
        if not path.endswith(".csv"):
            continue
        target = Path(path) if Path(path).is_absolute() else PROJECT_ROOT / path
        result = validate_entry_file(
            target,
            seed_csv_path=seed_csv_path,
            entries_dir=entries_dir,
            check_source=check_source,
        )
        validation_results.append(result.to_dict())

    review = {
        "author": author,
        "changed_files": list(changed_files),
        "allowed": allowed,
        "violations": violations,
        "validation_results": validation_results,
        "invalid_count": sum(1 for result in validation_results if not result["valid"]),
        "source_check": "enabled" if check_source else "disabled",
        "entries_dir": str(entries_dir),
    }
    review["comment"] = build_review_comment(review)
    return review


def _read_changed_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="共创 PR 审核逻辑（文件分类与留言模板）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify_parser = subparsers.add_parser("classify", help="只做文件分类，不依赖第三方包")
    classify_parser.add_argument("--changed-file-list", type=Path, required=True, help="每行一个变更文件路径的文本文件")
    classify_parser.add_argument("--entries-dir", type=Path, default=DEFAULT_ENTRIES_DIR)
    classify_parser.add_argument("--json", action="store_true")

    review_parser = subparsers.add_parser("review", help="文件分类 + 条目校验 + 生成留言")
    review_parser.add_argument("--changed-file-list", type=Path, required=True)
    review_parser.add_argument("--author", default="unknown")
    review_parser.add_argument("--seed", type=Path, default=DEFAULT_SEED_PATH)
    review_parser.add_argument("--entries-dir", type=Path, default=DEFAULT_ENTRIES_DIR)
    review_parser.add_argument("--check-source", action="store_true")
    review_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    changed = _read_changed_list(args.changed_file_list)

    if args.command == "classify":
        allowed, violations = classify_changed_files(changed, entries_dir=args.entries_dir)
        payload = {"allowed": allowed, "violations": violations}
    else:
        payload = build_review_payload(
            changed,
            author=args.author,
            seed_csv_path=args.seed,
            entries_dir=args.entries_dir,
            check_source=args.check_source,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
