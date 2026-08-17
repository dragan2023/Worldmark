"""Tests for scripts/import_contribution_entries.py (phase 04 merge & publish)."""

import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.import_contribution_entries import (
    PROJECT_ROOT,
    import_entries,
    main,
)
from scripts.validate_contribution_entry import EXPECTED_COLUMNS

VALID_DESCRIPTION = (
    "在作品中的重要地位：该地点是作品的核心空间。\n"
    "主要出现的情节：主角在此展开关键行动。\n"
    "现实地标介绍：这里是可定位的真实地点。"
)


def entry_row(**overrides) -> dict[str, str]:
    row = {
        "ip_type": "game",
        "work_title": "示例游戏",
        "aliases": "",
        "landmark_name": "示例古建",
        "country_code": "CN",
        "country_name": "中国",
        "province_name": "山西省",
        "city_name": "大同市",
        "district_name": "",
        "normalized_address": "山西省大同市示例街 1 号",
        "latitude": "",
        "longitude": "",
        "description": VALID_DESCRIPTION,
        "transit_text": "",
        "landmark_kind": "作品场景",
        "source_url": "https://example.org/source",
        "source_publisher": "示例文旅局",
        "source_title": "示例来源",
        "source_type": "official",
        "accessed_at": "2026-08-10T09:00:00+08:00",
        "license_note": "",
        "claim_scope": "work_association",
    }
    row.update(overrides)
    return row


def write_entry(tmp_path, filename="example-work--example-landmark.csv", subdir="game", **overrides):
    entries_dir = tmp_path / "entries"
    target_dir = entries_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXPECTED_COLUMNS, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerow(entry_row(**overrides))
    return path, entries_dir


def write_seed(tmp_path, rows=None):
    seed = tmp_path / "seed.csv"
    with open(seed, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXPECTED_COLUMNS, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in rows or []:
            writer.writerow(row)
    return seed


def write_content(tmp_path, items=None):
    content = tmp_path / "content.json"
    body = ",\n  ".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in (items or []))
    content.write_text("[\n  " + body + "\n]\n", encoding="utf-8")
    return content


def contributors_file(tmp_path):
    return tmp_path / "contributors.json"


def run_import(tmp_path, contributor="octocat", today="2026-08-17", **kwargs):
    return import_entries(
        entries_dir=kwargs.pop("entries_dir", tmp_path / "entries"),
        seed_path=kwargs.pop("seed", write_seed(tmp_path)),
        content_path=kwargs.pop("content", write_content(tmp_path)),
        contributors_file=kwargs.pop("contributors", contributors_file(tmp_path)),
        contributor=contributor,
        today=today,
        **kwargs,
    )


def seed_rows(seed):
    return list(csv.DictReader(io.StringIO(seed.read_text(encoding="utf-8-sig"))))


# --- basic import ---


def test_import_appends_seed_content_and_archives(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    seed = write_seed(tmp_path)
    content = write_content(tmp_path)
    contrib = contributors_file(tmp_path)
    report = import_entries(entries_dir, seed, content, contrib, contributor="octocat", today="2026-08-17")

    assert report.imported == ["game/example-work--example-landmark.csv"]
    assert report.invalid == []
    rows = seed_rows(seed)
    assert len(rows) == 1
    assert rows[0]["work_title"] == "示例游戏"
    assert rows[0]["landmark_name"] == "示例古建"

    items = json.loads(content.read_text(encoding="utf-8"))
    assert len(items) == 1
    assert items[0]["work_title"] == "示例游戏"
    assert items[0]["description"] == VALID_DESCRIPTION

    archived = entries_dir / "archive" / "2026-08-17" / "example-work--example-landmark.csv"
    assert archived.exists()
    assert not path.exists()

    manifest = json.loads((entries_dir / "archive" / "2026-08-17" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["imports"][0]["contributor"] == "octocat"
    assert manifest["imports"][0]["work_title"] == "示例游戏"

    data = json.loads(contrib.read_text(encoding="utf-8"))
    assert data == {
        "contributors": [
            {
                "username": "octocat",
                "github_url": "https://github.com/octocat",
                "first_merged_at": "2026-08-17",
                "merged_entries": 1,
            }
        ]
    }


def test_seed_bom_and_crlf_preserved(tmp_path):
    _, entries_dir = write_entry(tmp_path)
    seed = write_seed(tmp_path)
    content = write_content(tmp_path)
    import_entries(entries_dir, seed, content, contributors_file(tmp_path), contributor="octocat", today="2026-08-17")
    raw = seed.read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf"  # UTF-8 BOM
    assert b"\r\n" in raw
    header_line = raw.split(b"\r\n", 1)[0]
    assert header_line.startswith(b'\xef\xbb\xbf"ip_type","work_title"')


def test_import_is_idempotent(tmp_path):
    _, entries_dir = write_entry(tmp_path)
    seed = write_seed(tmp_path)
    content = write_content(tmp_path)
    contrib = contributors_file(tmp_path)
    import_entries(entries_dir, seed, content, contrib, contributor="octocat", today="2026-08-17")
    report2 = import_entries(entries_dir, seed, content, contrib, contributor="octocat", today="2026-08-17")

    assert report2.imported == []
    assert len(seed_rows(seed)) == 1  # no duplicate row
    archive_dir = entries_dir / "archive" / "2026-08-17"
    assert len(list(archive_dir.glob("*.csv"))) == 1
    manifest = json.loads((archive_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["imports"]) == 1
    data = json.loads(contrib.read_text(encoding="utf-8"))
    assert data["contributors"][0]["merged_entries"] == 1


def test_second_entry_same_batch_merges(tmp_path):
    _, entries_dir = write_entry(tmp_path, filename="a--a.csv")
    seed = write_seed(tmp_path)
    content = write_content(tmp_path)
    contrib = contributors_file(tmp_path)
    import_entries(entries_dir, seed, content, contrib, contributor="octocat", today="2026-08-17")
    write_entry(tmp_path, filename="b--b.csv", work_title="示例游戏2", landmark_name="另一处古建")
    report = import_entries(entries_dir, seed, content, contrib, contributor="octocat", today="2026-08-17")

    assert report.imported == ["game/b--b.csv"]
    assert len(seed_rows(seed)) == 2
    manifest = json.loads((entries_dir / "archive" / "2026-08-17" / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["imports"]) == 2
    data = json.loads(contrib.read_text(encoding="utf-8"))
    assert data["contributors"][0]["merged_entries"] == 2


def test_import_preserves_existing_seed_and_content(tmp_path):
    _, entries_dir = write_entry(tmp_path, work_title="新作品", landmark_name="新地标")
    existing = entry_row(work_title="既有作品", landmark_name="既有地标")
    seed = write_seed(tmp_path, rows=[existing])
    content = write_content(tmp_path, [{"ip_type": "game", "work_title": "既有作品", "landmark_name": "既有地标", "description": "既有简介"}])
    import_entries(entries_dir, seed, content, contributors_file(tmp_path), contributor="octocat", today="2026-08-17")

    rows = seed_rows(seed)
    assert len(rows) == 2
    assert {row["landmark_name"] for row in rows} == {"既有地标", "新地标"}
    items = json.loads(content.read_text(encoding="utf-8"))
    assert len(items) == 2
    assert any(item["landmark_name"] == "新地标" for item in items)


def test_import_updates_existing_content_description(tmp_path):
    _, entries_dir = write_entry(tmp_path, work_title="既有作品", landmark_name="既有地标")
    content = write_content(tmp_path, [{"ip_type": "game", "work_title": "既有作品", "landmark_name": "既有地标", "description": "旧简介"}])
    import_entries(entries_dir, write_seed(tmp_path), content, contributors_file(tmp_path), contributor="octocat", today="2026-08-17")
    items = json.loads(content.read_text(encoding="utf-8"))
    assert len(items) == 1
    assert items[0]["description"] == VALID_DESCRIPTION


# --- duplicates and invalid files ---


def test_import_skips_duplicate_against_seed(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    seed = write_seed(tmp_path, rows=[entry_row()])
    content = write_content(tmp_path)
    contrib = contributors_file(tmp_path)
    report = import_entries(entries_dir, seed, content, contrib, contributor="octocat", today="2026-08-17")

    assert report.imported == []
    assert report.skipped_duplicate == ["game/example-work--example-landmark.csv"]
    assert report.invalid == []
    assert path.exists()  # not archived
    assert len(seed_rows(seed)) == 1
    assert not contrib.exists()


def test_import_skips_invalid_entry(tmp_path):
    path, entries_dir = write_entry(tmp_path, ip_type="novel")
    seed = write_seed(tmp_path)
    content = write_content(tmp_path)
    report = import_entries(entries_dir, seed, content, contributors_file(tmp_path), contributor="octocat", today="2026-08-17")

    assert report.invalid == ["game/example-work--example-landmark.csv"]
    assert report.imported == []
    assert path.exists()
    assert len(seed_rows(seed)) == 0
    assert not (entries_dir / "archive").exists()


def test_import_without_contributor_still_imports(tmp_path):
    _, entries_dir = write_entry(tmp_path)
    seed = write_seed(tmp_path)
    content = write_content(tmp_path)
    contrib = contributors_file(tmp_path)
    report = import_entries(entries_dir, seed, content, contrib, contributor=None, today="2026-08-17")

    assert len(report.imported) == 1
    assert len(seed_rows(seed)) == 1
    assert not contrib.exists()
    manifest = json.loads((entries_dir / "archive" / "2026-08-17" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["imports"][0]["contributor"] is None


def test_contributor_upsert_preserves_first_merged_at(tmp_path):
    _, entries_dir = write_entry(tmp_path)
    write_entry(tmp_path, filename="b--b.csv", work_title="示例游戏2", landmark_name="另一处古建")
    seed = write_seed(tmp_path)
    content = write_content(tmp_path)
    contrib = contributors_file(tmp_path)
    contrib.write_text(
        json.dumps(
            {
                "contributors": [
                    {
                        "username": "octocat",
                        "github_url": "https://github.com/octocat",
                        "first_merged_at": "2026-08-01",
                        "merged_entries": 5,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    import_entries(entries_dir, seed, content, contrib, contributor="octocat", today="2026-08-17")

    data = json.loads(contrib.read_text(encoding="utf-8"))
    assert len(data["contributors"]) == 1
    assert data["contributors"][0]["first_merged_at"] == "2026-08-01"
    assert data["contributors"][0]["merged_entries"] == 7


def test_dry_run_writes_nothing(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    seed = write_seed(tmp_path)
    content = write_content(tmp_path)
    contrib = contributors_file(tmp_path)
    report = import_entries(entries_dir, seed, content, contrib, contributor="octocat", today="2026-08-17", dry_run=True)

    assert report.imported == ["game/example-work--example-landmark.csv"]
    assert path.exists()
    assert len(seed_rows(seed)) == 0
    assert json.loads(content.read_text(encoding="utf-8")) == []
    assert not contrib.exists()
    assert not (entries_dir / "archive").exists()


def test_archive_files_are_not_rescanned(tmp_path):
    _, entries_dir = write_entry(tmp_path)
    seed = write_seed(tmp_path)
    content = write_content(tmp_path)
    import_entries(entries_dir, seed, content, contributors_file(tmp_path), contributor="octocat", today="2026-08-17")
    # The archived copy must be ignored by the next scan (neither imported nor invalid).
    report = import_entries(entries_dir, seed, content, contributors_file(tmp_path), contributor="octocat", today="2026-08-17")
    assert report.imported == []
    assert report.invalid == []
    assert report.skipped_duplicate == []


# --- CLI ---


def test_main_cli_imports_and_reports(capsys, tmp_path):
    _, entries_dir = write_entry(tmp_path)
    seed = write_seed(tmp_path)
    content = write_content(tmp_path)
    contrib = contributors_file(tmp_path)
    exit_code = main(
        [
            "--contributor",
            "octocat",
            "--entries-dir",
            str(entries_dir),
            "--seed",
            str(seed),
            "--content",
            str(content),
            "--contributors-file",
            str(contrib),
            "--today",
            "2026-08-17",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Imported 1 entry file(s)" in out
    assert "octocat" in out
    assert len(seed_rows(seed)) == 1


def test_main_cli_returns_1_for_invalid(capsys, tmp_path):
    _, entries_dir = write_entry(tmp_path, ip_type="novel")
    exit_code = main(
        [
            "--entries-dir",
            str(entries_dir),
            "--seed",
            str(write_seed(tmp_path)),
            "--content",
            str(write_content(tmp_path)),
            "--contributors-file",
            str(contributors_file(tmp_path)),
        ]
    )
    assert exit_code == 1
    assert "Invalid entry" in capsys.readouterr().out


def test_main_cli_utf8_subprocess(tmp_path):
    _, entries_dir = write_entry(tmp_path)
    seed = write_seed(tmp_path)
    content = write_content(tmp_path)
    contrib = contributors_file(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "import_contribution_entries.py"),
            "--contributor",
            "octocat",
            "--entries-dir",
            str(entries_dir),
            "--seed",
            str(seed),
            "--content",
            str(content),
            "--contributors-file",
            str(contrib),
            "--today",
            "2026-08-17",
        ],
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8")
    assert "示例" not in proc.stdout.decode("utf-8")  # output is path/ASCII summary
    assert len(seed_rows(seed)) == 1
    data = json.loads(contrib.read_text(encoding="utf-8"))
    assert data["contributors"][0]["username"] == "octocat"
