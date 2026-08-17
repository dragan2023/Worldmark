"""Validate one or more community IP-landmark entry CSV files.

An entry file is a single-row CSV that must exactly match the columns of
``data/templates/landmark_candidate_template.csv`` and live under
``data/contributions/entries/<ip_type>/<work-slug>--<landmark-slug>.csv``.

This validator has no database dependency: the same rules are used by the
local Harness prompt pack and by the GitHub Actions review bot.

Run from anywhere with the project virtualenv::

    .venv\\Scripts\\python.exe scripts\\validate_contribution_entry.py --file <path> [--json]
    .venv\\Scripts\\python.exe scripts\\validate_contribution_entry.py --dir data\\contributions\\entries [--json]
    .venv\\Scripts\\python.exe scripts\\validate_contribution_entry.py --changed-files <path> [<path> ...] [--json]

Exit code is 0 when every validated file is valid, 1 otherwise.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.import_landmarks import CandidateRow  # noqa: E402
from pydantic import ValidationError  # noqa: E402

DEFAULT_SEED_PATH = PROJECT_ROOT / "data" / "seed" / "landmarks_verified.csv"
DEFAULT_ENTRIES_DIR = PROJECT_ROOT / "data" / "contributions" / "entries"

EXPECTED_COLUMNS: tuple[str, ...] = (
    "ip_type",
    "work_title",
    "aliases",
    "landmark_name",
    "country_code",
    "country_name",
    "province_name",
    "city_name",
    "district_name",
    "normalized_address",
    "latitude",
    "longitude",
    "description",
    "transit_text",
    "landmark_kind",
    "source_url",
    "source_publisher",
    "source_title",
    "source_type",
    "accessed_at",
    "license_note",
    "claim_scope",
)

ENTRY_FILENAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*--[a-z0-9]+(-[a-z0-9]+)*\.csv$")

THREE_PART_PREFIXES: tuple[str, ...] = ("在作品中的重要地位：", "主要出现的情节：", "现实地标介绍：")

IP_TYPE_DIRECTORIES: frozenset[str] = frozenset({"literature", "game", "screen"})

DUPLICATE_KEY_COLUMNS: tuple[str, ...] = ("ip_type", "work_title", "landmark_name", "normalized_address")


@dataclass(frozen=True)
class EntryValidation:
    file: str
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "summary": self.summary,
        }


def _read_rows(path: Path) -> tuple[list[str] | None, list[dict[str, str | None]]]:
    """Return (fieldnames, rows) for a UTF-8 (with or without BOM) CSV file."""
    raw = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    return reader.fieldnames, list(reader)


def _duplicate_key(row: dict[str, str | None]) -> str:
    parts = []
    for column in DUPLICATE_KEY_COLUMNS:
        value = (row.get(column) or "").strip().lower()
        parts.append(value)
    return "|".join(parts)


def _row_key_complete(row: dict[str, str | None]) -> bool:
    return all((row.get(column) or "").strip() for column in DUPLICATE_KEY_COLUMNS)


def _collect_duplicate_keys(
    seed_csv_path: Path, entries_dir: Path, exclude: Path | None = None
) -> dict[str, str]:
    """Map normalized duplicate keys to the seed table or entry file they came from."""
    keys: dict[str, str] = {}
    if seed_csv_path.exists():
        try:
            _, seed_rows = _read_rows(seed_csv_path)
        except Exception:
            seed_rows = []
        for row in seed_rows:
            if _row_key_complete(row):
                keys.setdefault(_duplicate_key(row), str(seed_csv_path))
    if entries_dir.exists():
        for entry_path in sorted(entries_dir.rglob("*.csv")):
            if exclude is not None and entry_path.resolve() == exclude.resolve():
                continue
            try:
                _, rows = _read_rows(entry_path)
            except Exception:
                continue
            for row in rows:
                if _row_key_complete(row):
                    keys.setdefault(_duplicate_key(row), str(entry_path))
    return keys


def validate_entry_file(
    path: Path,
    seed_csv_path: Path = DEFAULT_SEED_PATH,
    entries_dir: Path = DEFAULT_ENTRIES_DIR,
    check_source: bool = False,
) -> EntryValidation:
    """Validate a single entry file without touching the database."""
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, object] = {"checks": {}}

    path = path.resolve()
    if not path.exists():
        return EntryValidation(str(path), False, ("文件不存在：%s" % path,), (), summary)

    # 1. Must live under entries_dir/<ip_type>/.
    parent = path.parent
    in_entries_dir = parent.parent.resolve() == entries_dir.resolve() and parent.name in IP_TYPE_DIRECTORIES
    summary["checks"]["directory"] = in_entries_dir
    if not in_entries_dir:
        errors.append(
            "文件必须位于 %s/<ip_type>/ 目录下（ip_type 只能是 %s）"
            % (entries_dir, ", ".join(sorted(IP_TYPE_DIRECTORIES)))
        )

    # 2. Filename must be <work-slug>--<landmark-slug>.csv.
    filename_ok = bool(ENTRY_FILENAME_RE.match(path.name))
    summary["checks"]["filename"] = filename_ok
    if not filename_ok:
        errors.append("文件名必须符合 <work-slug>--<landmark-slug>.csv（全小写，单词用连字符分隔）")

    # 3. Read the CSV and check the header.
    try:
        fieldnames, rows = _read_rows(path)
    except UnicodeDecodeError:
        summary["checks"].update({"header": False, "row_count": False, "fields": False})
        errors.append("文件不是 UTF-8 编码（允许带 BOM）")
        return EntryValidation(str(path), not errors, tuple(errors), tuple(warnings), summary)

    header_ok = tuple(fieldnames or []) == EXPECTED_COLUMNS
    summary["checks"]["header"] = header_ok
    if not header_ok:
        errors.append(
            "表头必须与 data/templates/landmark_candidate_template.csv 完全一致（当前 %d 列）"
            % len(fieldnames or [])
        )

    row_count_ok = len(rows) == 1
    summary["checks"]["row_count"] = row_count_ok
    if not row_count_ok:
        errors.append("条目文件必须且只能包含一行数据")

    # 4. Field-level validation reusing the project's CandidateRow contract.
    fields_ok = False
    if header_ok and row_count_ok:
        try:
            CandidateRow.model_validate(rows[0])
            fields_ok = True
        except ValidationError as exc:
            for error in exc.errors(include_url=False):
                location = ".".join(str(part) for part in error["loc"])
                errors.append("字段 %s: %s" % (location, error["msg"]))
    # The ip_type value must match the parent directory the file lives in.
    if header_ok and rows and in_entries_dir:
        ip_type = (rows[0].get("ip_type") or "").strip()
        if ip_type and ip_type != parent.name:
            errors.append(
                "文件位于 %s/ 子目录，但 ip_type 为 %s，二者必须一致" % (parent.name, ip_type)
            )
            summary["checks"]["directory"] = False
    summary["checks"]["fields"] = fields_ok

    # 5. Three-part original description.
    three_part_ok = False
    if header_ok and rows:
        description = rows[0].get("description") or ""
        three_part_ok = all(prefix in description for prefix in THREE_PART_PREFIXES)
    summary["checks"]["three_part_description"] = three_part_ok
    if not three_part_ok:
        errors.append("description 必须包含三段式前缀：%s" % "、".join(THREE_PART_PREFIXES))

    # 6. Duplicate check against the seed table and other entry files.
    duplicate_ok = True
    if header_ok and rows and _row_key_complete(rows[0]):
        owners = _collect_duplicate_keys(seed_csv_path, entries_dir, exclude=path)
        key = _duplicate_key(rows[0])
        if key in owners:
            duplicate_ok = False
            errors.append(
                "与既有数据重复（%s）：%s / %s / %s"
                % (owners[key], rows[0].get("work_title"), rows[0].get("landmark_name"), rows[0].get("normalized_address"))
            )
    summary["checks"]["duplicate"] = duplicate_ok

    # 7. Optional source reachability check (advisory only, never blocks).
    if check_source and header_ok and rows:
        source_url = rows[0].get("source_url") or ""
        if source_url:
            try:
                import httpx

                with httpx.Client(follow_redirects=True, timeout=10.0) as client:
                    response = client.request("HEAD", source_url)
                if response.status_code >= 400:
                    warnings.append("来源 URL 返回状态 %d（仅提醒）" % response.status_code)
            except Exception as exc:  # noqa: BLE001 - reachability is advisory
                warnings.append("来源 URL 可达性检查失败：%s（仅提醒）" % exc.__class__.__name__)
    summary["checks"]["source_reachable"] = True

    if rows and header_ok:
        row = rows[0]
        for column in ("ip_type", "work_title", "landmark_name", "country_code", "normalized_address", "source_url"):
            summary[column] = row.get(column) or ""

    return EntryValidation(str(path), not errors, tuple(errors), tuple(warnings), summary)


def _print_human(result: EntryValidation) -> None:
    status = "通过" if result.valid else "未通过"
    print("%s  %s" % ("[OK]" if result.valid else "[FAIL]", result.file))
    for error in result.errors:
        print("    - %s" % error)
    for warning in result.warnings:
        print("    ! %s" % warning)


def main(argv: list[str] | None = None) -> int:
    # Force UTF-8 stdout so --json output is byte-clean on Windows consoles/pipes
    # (GitHub Actions consumes this JSON directly).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="校验共创 IP 地标条目 CSV 文件")
    parser.add_argument("--file", type=Path, help="校验单个条目文件")
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_ENTRIES_DIR,
        help="校验目录下的全部条目文件（默认 data/contributions/entries）",
    )
    parser.add_argument("--changed-files", nargs="*", type=Path, help="校验指定的一组条目文件")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED_PATH, help="用于重复检查的种子 CSV 路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument("--check-source", action="store_true", help="对来源 URL 做受限可达性检查（仅提醒）")
    args = parser.parse_args(argv)

    if args.file is not None:
        targets = [args.file]
    elif args.changed_files is not None:
        targets = list(args.changed_files)
    elif args.dir.exists():
        targets = sorted(args.dir.rglob("*.csv"))
    else:
        targets = []

    results = [
        validate_entry_file(
            target, seed_csv_path=args.seed, entries_dir=args.dir, check_source=args.check_source
        )
        for target in targets
    ]

    if args.json:
        payload = results[0].to_dict() if len(results) == 1 else [item.to_dict() for item in results]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for result in results:
            _print_human(result)
        passed = sum(1 for result in results if result.valid)
        print("共 %d 个文件，通过 %d 个。" % (len(results), passed))

    return 0 if all(result.valid for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())


