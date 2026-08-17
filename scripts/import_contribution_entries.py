"""Import accepted community contribution entries into the seed data (phase 04).

The publish pipeline runs this script after a contribution PR is merged. It
performs the deterministic, idempotent merge of entry files under
data/contributions/entries/ into the project-maintained seed data:

1. Re-validate every entry file with scripts/validate_contribution_entry.py
   (defense in depth; the review bot already validated the PR).
2. Append non-duplicate rows to data/seed/landmarks_verified.csv. A row is
   a duplicate when its normalized key (ip_type + work_title + landmark_name +
   normalized_address) already exists in the seed table.
3. Upsert the three-part description into data/seed/landmark_content.json
   keyed by ip_type + work_title + landmark_name.
4. Move processed files into data/contributions/entries/archive/YYYY-MM-DD/
   and write a per-batch manifest.json that records which contributor
   authored which imported landmark key (used by seed_initial_landmarks to
   write LandmarkContribution attribution).
5. Upsert the --contributor GitHub username into
   data/contributions/contributors.json.

The script is idempotent: files already under archive/ are skipped, duplicate
keys are skipped, and the contributor counter only grows by newly imported
entries. Write scope is limited to data/seed/, contributors.json and the
entries directory (including archive/) -- it never touches app/ logic or the
database.

Run from anywhere with the project virtualenv::

    .venv\\Scripts\\python.exe scripts\\import_contribution_entries.py --contributor octocat
    .venv\\Scripts\\python.exe scripts\\import_contribution_entries.py --contributor octocat --dry-run
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_contribution_entry import (  # noqa: E402
    DUPLICATE_KEY_COLUMNS,
    EXPECTED_COLUMNS,
    validate_entry_file,
)

DEFAULT_SEED_PATH = PROJECT_ROOT / "data" / "seed" / "landmarks_verified.csv"
DEFAULT_CONTENT_PATH = PROJECT_ROOT / "data" / "seed" / "landmark_content.json"
DEFAULT_ENTRIES_DIR = PROJECT_ROOT / "data" / "contributions" / "entries"
DEFAULT_CONTRIBUTORS_FILE = PROJECT_ROOT / "data" / "contributions" / "contributors.json"
MANIFEST_NAME = "manifest.json"


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a UTF-8 (with or without BOM) CSV without newline translation."""
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    return list(reader.fieldnames or []), list(reader)


def _duplicate_key(row: dict[str, str | None]) -> str:
    parts = []
    for column in DUPLICATE_KEY_COLUMNS:
        parts.append((row.get(column) or "").strip().lower())
    return "|".join(parts)


def _write_seed_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    """Write the seed table with its original BOM + CRLF + fully-quoted style."""
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fieldnames, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)
    path.write_bytes(out.getvalue().encode("utf-8-sig"))


def _load_content(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_content(items: list[dict[str, str]]) -> str:
    body = ",\n  ".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in items)
    return "[\n  " + body + "\n]\n"


def _content_key(item: dict[str, object]) -> str:
    return "|".join(str(item.get(column) or "") for column in ("ip_type", "work_title", "landmark_name"))


def _upsert_content(items: list[dict[str, str]], row: dict[str, str]) -> bool:
    """Upsert one three-part description; returns True when the list changed."""
    key = _content_key(row)
    for item in items:
        if _content_key(item) == key:
            if item.get("description") == row.get("description"):
                return False
            item["description"] = row.get("description") or ""
            return True
    items.append(
        {
            "ip_type": row.get("ip_type") or "",
            "work_title": row.get("work_title") or "",
            "landmark_name": row.get("landmark_name") or "",
            "description": row.get("description") or "",
        }
    )
    return True


def _load_manifest(manifest_path: Path) -> dict[str, object]:
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"batch_date": manifest_path.parent.name, "imports": []}


def _save_manifest(manifest_path: Path, manifest: dict[str, object]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_contributors(path: Path) -> dict[str, list[dict[str, object]]]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("contributors"), list):
                return data
        except Exception:
            pass
    return {"contributors": []}


def _upsert_contributor(path: Path, username: str, added_entries: int, today: str) -> None:
    """Upsert one GitHub username; only the cumulative counter grows on re-runs."""
    data = _load_contributors(path)
    contributors = data["contributors"]
    for entry in contributors:
        if entry.get("username") == username:
            entry["merged_entries"] = int(entry.get("merged_entries") or 0) + added_entries
            break
    else:
        contributors.append(
            {
                "username": username,
                "github_url": "https://github.com/" + username,
                "first_merged_at": today,
                "merged_entries": added_entries,
            }
        )
    contributors.sort(key=lambda item: str(item.get("username") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass
class ImportReport:
    imported: list[str] = field(default_factory=list)
    skipped_duplicate: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)
    added_to_contributor: int = 0
    manifest_written: bool = False


def import_entries(
    entries_dir: Path,
    seed_path: Path,
    content_path: Path,
    contributors_file: Path,
    archive_root: Path | None = None,
    contributor: str | None = None,
    today: str | None = None,
    dry_run: bool = False,
) -> ImportReport:
    """Merge entry files under entries_dir into the seed data (idempotent)."""
    entries_dir = entries_dir.resolve()
    archive_root = (archive_root or entries_dir / "archive").resolve()
    today = today or date.today().isoformat()
    report = ImportReport()

    seed_fieldnames, seed_rows = _read_csv_rows(seed_path)
    seed_keys = {_duplicate_key(row) for row in seed_rows}
    content_items = _load_content(content_path)
    manifest_path = archive_root / today / MANIFEST_NAME
    manifest = _load_manifest(manifest_path)
    known_manifest_files = {str(item.get("file")) for item in manifest.get("imports", [])}

    entry_files = sorted(
        path
        for path in entries_dir.rglob("*.csv")
        if "archive" not in path.relative_to(entries_dir).parts
    )

    for entry_path in entry_files:
        relative_name = entry_path.relative_to(entries_dir).as_posix()
        validation = validate_entry_file(entry_path, seed_csv_path=seed_path, entries_dir=entries_dir)
        if not validation.valid:
            if not validation.summary.get("checks", {}).get("duplicate", True):
                report.skipped_duplicate.append(relative_name)
            else:
                report.invalid.append(relative_name)
            continue

        row = _read_csv_rows(entry_path)[1][0]
        key = _duplicate_key(row)
        if key in seed_keys:
            report.skipped_duplicate.append(relative_name)
            continue

        report.imported.append(relative_name)
        if dry_run:
            continue

        seed_rows.append(row)
        seed_keys.add(key)
        _upsert_content(content_items, row)

        batch_dir = archive_root / today
        batch_dir.mkdir(parents=True, exist_ok=True)
        target = batch_dir / entry_path.name
        if target.exists():
            target.unlink()
        shutil.move(str(entry_path), str(target))
        report.archived.append(relative_name)

        if relative_name not in known_manifest_files:
            manifest.setdefault("imports", []).append(
                {
                    "file": relative_name,
                    "contributor": contributor,
                    "ip_type": row.get("ip_type") or "",
                    "work_title": row.get("work_title") or "",
                    "landmark_name": row.get("landmark_name") or "",
                }
            )
            known_manifest_files.add(relative_name)

    if dry_run or not report.imported:
        return report

    _write_seed_csv(seed_path, seed_fieldnames, seed_rows)
    content_path.write_text(_dump_content(content_items), encoding="utf-8")
    _save_manifest(manifest_path, manifest)
    report.manifest_written = True

    if contributor:
        report.added_to_contributor = len(report.imported)
        _upsert_contributor(contributors_file, contributor, len(report.imported), today)
    return report


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="把已合入的共创条目并入种子数据并更新共创者名单")
    parser.add_argument("--contributor", help="PR 作者的 GitHub 用户名（用于共创者名单与署名）")
    parser.add_argument("--entries-dir", type=Path, default=DEFAULT_ENTRIES_DIR)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT_PATH)
    parser.add_argument("--contributors-file", type=Path, default=DEFAULT_CONTRIBUTORS_FILE)
    parser.add_argument("--archive-root", type=Path, default=None, help="归档根目录（默认 entries 目录下的 archive）")
    parser.add_argument("--today", default=None, help="归档/名单日期 YYYY-MM-DD（默认今天，测试用）")
    parser.add_argument("--dry-run", action="store_true", help="只报告将要导入的文件，不写任何文件")
    args = parser.parse_args(argv)

    report = import_entries(
        entries_dir=args.entries_dir,
        seed_path=args.seed,
        content_path=args.content,
        contributors_file=args.contributors_file,
        archive_root=args.archive_root,
        contributor=args.contributor,
        today=args.today,
        dry_run=args.dry_run,
    )

    print("Imported %d entry file(s): %s" % (len(report.imported), ", ".join(report.imported) or "none"))
    for name in report.skipped_duplicate:
        print("Skipped duplicate: %s" % name)
    for name in report.invalid:
        print("Invalid entry (not imported): %s" % name)
    print("Archived %d file(s) under %s/%s" % (len(report.archived), args.archive_root or args.entries_dir / "archive", args.today or date.today().isoformat()))
    if report.added_to_contributor:
        print("Contributor %s: +%d merged entries" % (args.contributor, report.added_to_contributor))
    if args.dry_run:
        print("Dry run: no files were written.")
    return 1 if report.invalid else 0


if __name__ == "__main__":
    sys.exit(main())
