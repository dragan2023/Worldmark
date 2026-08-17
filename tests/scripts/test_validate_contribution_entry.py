"""Tests for scripts/validate_contribution_entry.py (phase 01 of the contribution workflow plan)."""

import csv
import json
import os
import subprocess
import sys

from scripts.validate_contribution_entry import (
    DEFAULT_SEED_PATH,
    EXPECTED_COLUMNS,
    PROJECT_ROOT,
    main,
    validate_entry_file,
)

TEMPLATE_PATH = PROJECT_ROOT / "data" / "templates" / "landmark_candidate_template.csv"
SEED_PATH = PROJECT_ROOT / "data" / "seed" / "landmarks_verified.csv"

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


def write_entry(
    tmp_path,
    filename: str = "example-work--example-landmark.csv",
    subdir: str = "game",
    **overrides,
):
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


def validate(
    tmp_path,
    filename="example-work--example-landmark.csv",
    subdir="game",
    check_source=False,
    **overrides,
):
    path, entries_dir = write_entry(tmp_path, filename=filename, subdir=subdir, **overrides)
    return validate_entry_file(
        path, seed_csv_path=empty_seed(tmp_path), entries_dir=entries_dir, check_source=check_source
    )


# --- contract: expected columns stay in sync with the official template ---


def test_expected_columns_match_official_template():
    raw = TEMPLATE_PATH.read_text(encoding="utf-8-sig")
    header = next(csv.reader([raw.splitlines()[0]]))
    assert tuple(header) == EXPECTED_COLUMNS


# --- valid entries ---


def test_valid_entry_passes(tmp_path):
    result = validate(tmp_path)
    assert result.valid
    assert result.errors == ()
    assert result.summary["checks"]["fields"] is True
    assert result.summary["work_title"] == "示例游戏"


def test_blank_optional_coordinates_pass(tmp_path):
    result = validate(tmp_path, latitude="", longitude="")
    assert result.valid


def test_populated_coordinates_pass(tmp_path):
    result = validate(tmp_path, latitude="39.9", longitude="113.3")
    assert result.valid


# --- field-level failures ---


def test_missing_required_column_fails(tmp_path):
    result = validate(tmp_path, normalized_address="")
    assert not result.valid
    assert any("normalized_address" in error for error in result.errors)


def test_invalid_ip_type_fails(tmp_path):
    result = validate(tmp_path, ip_type="novel")
    assert not result.valid
    assert any("ip_type" in error for error in result.errors)


def test_invalid_country_code_fails(tmp_path):
    result = validate(tmp_path, country_code="CHN")
    assert not result.valid
    assert any("country_code" in error for error in result.errors)


def test_non_http_source_url_fails(tmp_path):
    result = validate(tmp_path, source_url="not-a-url")
    assert not result.valid
    assert any("source_url" in error for error in result.errors)


def test_invalid_accessed_at_fails(tmp_path):
    result = validate(tmp_path, accessed_at="2026-99-99")
    assert not result.valid
    assert any("accessed_at" in error for error in result.errors)


# --- content rules ---


def test_missing_three_part_description_fails(tmp_path):
    result = validate(tmp_path, description="只是一句普通简介")
    assert not result.valid
    assert any("三段式" in error for error in result.errors)
    assert result.summary["checks"]["three_part_description"] is False


# --- duplicate detection ---


def test_duplicate_with_seed_row_fails(tmp_path):
    seed_rows = list(csv.DictReader(SEED_PATH.read_text(encoding="utf-8-sig").splitlines()))
    first = seed_rows[0]
    path, entries_dir = write_entry(
        tmp_path,
        filename="seed-work--seed-landmark.csv",
        subdir=first["ip_type"],
        ip_type=first["ip_type"],
        work_title=first["work_title"],
        landmark_name=first["landmark_name"],
        normalized_address=first["normalized_address"],
        description=first["description"],
        source_url="https://example.org/another-source",
    )
    result = validate_entry_file(path, seed_csv_path=SEED_PATH, entries_dir=entries_dir)
    assert not result.valid
    assert any("重复" in error for error in result.errors)
    assert result.summary["checks"]["duplicate"] is False


def test_duplicate_with_other_entry_file_fails(tmp_path):
    path, entries_dir = write_entry(tmp_path, filename="example-work--example-landmark.csv")
    empty_seed_path = empty_seed(tmp_path)
    first = validate_entry_file(path, seed_csv_path=empty_seed_path, entries_dir=entries_dir)
    assert first.valid

    second_path = entries_dir / "game" / "another-work--same-landmark.csv"
    with open(second_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerow(entry_row())
    second = validate_entry_file(second_path, seed_csv_path=empty_seed_path, entries_dir=entries_dir)
    assert not second.valid
    assert any("重复" in error for error in second.errors)


# --- structure rules ---


def test_bad_filename_fails(tmp_path):
    result = validate(tmp_path, filename="Bad Name.csv")
    assert not result.valid
    assert result.summary["checks"]["filename"] is False


def test_filename_without_slug_separator_fails(tmp_path):
    result = validate(tmp_path, filename="example-landmark.csv")
    assert not result.valid
    assert result.summary["checks"]["filename"] is False


def test_file_outside_ip_type_subdir_fails(tmp_path):
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir(parents=True, exist_ok=True)
    path = entries_dir / "example-work--example-landmark.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerow(entry_row())
    result = validate_entry_file(path, seed_csv_path=empty_seed(tmp_path), entries_dir=entries_dir)
    assert not result.valid
    assert result.summary["checks"]["directory"] is False
    assert any("目录" in error for error in result.errors)


def test_ip_type_mismatch_with_parent_dir_fails(tmp_path):
    path, entries_dir = write_entry(tmp_path, subdir="literature")
    result = validate_entry_file(path, seed_csv_path=empty_seed(tmp_path), entries_dir=entries_dir)
    assert not result.valid
    assert result.summary["checks"]["directory"] is False
    assert any("二者必须一致" in error for error in result.errors)


def test_header_only_file_fails(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    path.write_text(",".join(EXPECTED_COLUMNS) + "\n", encoding="utf-8")
    result = validate_entry_file(path, seed_csv_path=empty_seed(tmp_path), entries_dir=entries_dir)
    assert not result.valid
    assert result.summary["checks"]["row_count"] is False


def test_two_data_rows_fails(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    lines = [",".join(EXPECTED_COLUMNS)]
    rows = [entry_row(), entry_row(landmark_name="另一处地标")]
    for row in rows:
        lines.append(",".join('"%s"' % (row[column].replace('"', '""')) for column in EXPECTED_COLUMNS))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = validate_entry_file(path, seed_csv_path=empty_seed(tmp_path), entries_dir=entries_dir)
    assert not result.valid
    assert result.summary["checks"]["row_count"] is False


def test_non_utf8_file_fails(tmp_path):
    path, entries_dir = write_entry(tmp_path)
    path.write_bytes(path.read_bytes().decode("utf-8").encode("gbk"))
    result = validate_entry_file(path, seed_csv_path=empty_seed(tmp_path), entries_dir=entries_dir)
    assert not result.valid
    assert any("UTF-8" in error for error in result.errors)


def test_missing_file_fails(tmp_path):
    entries_dir = tmp_path / "entries"
    result = validate_entry_file(entries_dir / "game" / "missing.csv", entries_dir=entries_dir)
    assert not result.valid
    assert any("不存在" in error for error in result.errors)


# --- optional source reachability ---


def test_source_reachability_warns_on_failure(tmp_path):
    # Port 1 is expected to refuse connections immediately; the check is advisory only.
    result = validate(tmp_path, source_url="http://127.0.0.1:1/", check_source=True)
    assert result.valid
    assert len(result.warnings) == 1
    assert "可达性" in result.warnings[0]


# --- CLI behaviour ---


def test_cli_json_single_valid_file(capsys, tmp_path):
    path, entries_dir = write_entry(tmp_path)
    exit_code = main(
        [
            "--file",
            str(path),
            "--seed",
            str(empty_seed(tmp_path)),
            "--dir",
            str(entries_dir),
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["file"] == str(path.resolve())


def test_cli_json_invalid_file_exit_code(capsys, tmp_path):
    path, entries_dir = write_entry(tmp_path, ip_type="novel")
    exit_code = main(
        [
            "--file",
            str(path),
            "--seed",
            str(empty_seed(tmp_path)),
            "--dir",
            str(entries_dir),
            "--json",
        ]
    )
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False


def test_cli_dir_scans_all_entries(capsys, tmp_path):
    write_entry(tmp_path, filename="example-work--example-landmark.csv")
    write_entry(tmp_path, filename="another-work--another-landmark.csv", landmark_name="另一处地标")
    entries_dir = tmp_path / "entries"
    exit_code = main(["--dir", str(entries_dir), "--seed", str(empty_seed(tmp_path)), "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 2
    assert all(item["valid"] for item in payload)


def test_cli_dir_reports_invalid_mixed(capsys, tmp_path):
    write_entry(tmp_path, filename="example-work--example-landmark.csv")
    write_entry(tmp_path, filename="another-work--another-landmark.csv", landmark_name="另一处地标", ip_type="novel")
    entries_dir = tmp_path / "entries"
    exit_code = main(["--dir", str(entries_dir), "--seed", str(empty_seed(tmp_path)), "--json"])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 2
    assert sum(1 for item in payload if item["valid"]) == 1


def test_cli_json_output_is_utf8_in_subprocess(tmp_path):
    # --json output must be byte-clean UTF-8 even when stdout is a Windows pipe.
    path, entries_dir = write_entry(tmp_path)
    env = {key: value for key, value in os.environ.items() if key != "PYTHONIOENCODING"}
    proc = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "validate_contribution_entry.py"),
            "--file",
            str(path),
            "--seed",
            str(empty_seed(tmp_path)),
            "--dir",
            str(entries_dir),
            "--json",
        ],
        capture_output=True,
        env=env,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout.decode("utf-8"))
    assert payload["valid"] is True
    assert payload["summary"]["work_title"] == "示例游戏"


def test_default_seed_path_points_at_repo_seed():
    assert DEFAULT_SEED_PATH == SEED_PATH
    assert SEED_PATH.exists()
