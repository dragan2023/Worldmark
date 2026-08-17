"""Tests for scripts/review_logic.py (phase 03 review bot pure logic)."""

import csv
import json
import subprocess
import sys

from scripts.review_logic import (
    DEFAULT_ENTRIES_DIR,
    PROMPT_PACK_PATH,
    PROJECT_ROOT,
    build_review_comment,
    build_review_payload,
    classify_changed_files,
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
        writer = csv.DictWriter(fh, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerow(entry_row(**overrides))
    return path, entries_dir


def empty_seed(tmp_path):
    seed = tmp_path / "seed.csv"
    seed.write_text(",".join(EXPECTED_COLUMNS) + "\n", encoding="utf-8")
    return seed


# --- classification (file lockdown) ---


def test_classify_allows_relative_entry_paths():
    allowed, violations = classify_changed_files(
        [
            "data/contributions/entries/game/black-myth-wukong--foguang-temple.csv",
            "data/contributions/entries/literature/luxun--baicaoyuan.csv",
        ]
    )
    assert allowed == [
        "data/contributions/entries/game/black-myth-wukong--foguang-temple.csv",
        "data/contributions/entries/literature/luxun--baicaoyuan.csv",
    ]
    assert violations == []


def test_classify_allows_absolute_paths_under_entries_dir(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    allowed, violations = classify_changed_files([str(path)], entries_dir=entries_dir)
    assert allowed == [str(path)]
    assert violations == []


def test_classify_flags_non_entry_files():
    allowed, violations = classify_changed_files(
        ["app/main.py", "data/seed/landmarks_verified.csv", "data/contributions/contributors.json"]
    )
    assert allowed == []
    assert len(violations) == 3


def test_classify_mixed_paths_and_blank_lines(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    allowed, violations = classify_changed_files(["", "  ", str(path), "README.md"], entries_dir=entries_dir)
    assert allowed == [str(path)]
    assert violations == ["README.md"]


# --- comment rendering ---


def test_comment_author_and_pass_lines(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    review = build_review_payload(
        [str(path)], author="octocat", seed_csv_path=empty_seed(tmp_path), entries_dir=entries_dir
    )
    comment = review["comment"]
    assert "@octocat" in comment
    assert "✅ 仅新增条目文件" in comment
    assert "✅ 1 个文件全部通过" in comment
    assert "✅ 无重复" in comment
    assert PROMPT_PACK_PATH in comment
    assert review["invalid_count"] == 0


def test_comment_lists_invalid_entry_errors(tmp_path):
    path, entries_dir = write_entry(tmp_path, description="只是一句普通简介")
    review = build_review_payload(
        [str(path)], author="octocat", seed_csv_path=empty_seed(tmp_path), entries_dir=entries_dir
    )
    comment = review["comment"]
    assert review["invalid_count"] == 1
    assert "❌ 1 个文件未通过" in comment
    assert "三段式" in comment
    assert "example-work--example-landmark.csv" in comment


def test_comment_lists_violations():
    review = {
        "author": "octocat",
        "violations": ["app/main.py", "README.md"],
        "validation_results": [],
        "source_check": "disabled",
        "entries_dir": str(DEFAULT_ENTRIES_DIR),
    }
    comment = build_review_comment(review)
    assert "❌ 发现 2 个越界文件" in comment
    assert "app/main.py" in comment
    assert "README.md" in comment
    assert "仅允许新增条目文件" in comment


def test_comment_flags_duplicates(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    seed = tmp_path / "seed.csv"
    seed.write_text(",".join(EXPECTED_COLUMNS) + "\n" + _quoted_row(entry_row()) + "\n", encoding="utf-8")
    review = build_review_payload([str(path)], author="octocat", seed_csv_path=seed, entries_dir=entries_dir)
    comment = review["comment"]
    assert "❌ 与既有数据重复" in comment
    assert review["invalid_count"] == 1


def _quoted_row(row):
    return ",".join('"%s"' % (row[column].replace('"', '""')) for column in EXPECTED_COLUMNS)


def test_comment_source_check_warning(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    review = build_review_payload(
        [str(path)],
        author="octocat",
        seed_csv_path=empty_seed(tmp_path),
        entries_dir=entries_dir,
        check_source=True,
    )
    comment = review["comment"]
    assert "来源可达性：⚠️ 已启用" in comment


# --- CLI ---


def test_cli_classify_json(capsys, tmp_path):
    changed_list = tmp_path / "changed.txt"
    changed_list.write_text("data/contributions/entries/game/a--b.csv\napp/main.py\n", encoding="utf-8")
    exit_code = main(["classify", "--changed-file-list", str(changed_list), "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["allowed"] == ["data/contributions/entries/game/a--b.csv"]
    assert payload["violations"] == ["app/main.py"]


def test_cli_review_json(capsys, tmp_path):
    path, entries_dir = write_entry(tmp_path)
    changed_list = tmp_path / "changed.txt"
    changed_list.write_text(str(path) + "\n", encoding="utf-8")
    exit_code = main(
        [
            "review",
            "--changed-file-list",
            str(changed_list),
            "--author",
            "octocat",
            "--seed",
            str(empty_seed(tmp_path)),
            "--entries-dir",
            str(entries_dir),
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["author"] == "octocat"
    assert payload["invalid_count"] == 0
    assert "@octocat" in payload["comment"]


def test_cli_review_json_utf8_subprocess(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    changed_list = tmp_path / "changed.txt"
    changed_list.write_text(str(path) + "\n", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "review_logic.py"),
            "review",
            "--changed-file-list",
            str(changed_list),
            "--author",
            "octocat",
            "--seed",
            str(empty_seed(tmp_path)),
            "--entries-dir",
            str(entries_dir),
            "--json",
        ],
        capture_output=True,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout.decode("utf-8"))
    assert payload["author"] == "octocat"
    assert "共创条目审核结果" in payload["comment"]
