"""Tests for the seed_initial_landmarks attribution step (phase 04)."""

import csv
import io
import json

from sqlalchemy import select

from app.models.contribution import LandmarkContribution
from app.scripts.seed_initial_landmarks import _load_attribution_manifests, _write_attributions
from app.services.import_landmarks import LandmarkImportService
from scripts.validate_contribution_entry import EXPECTED_COLUMNS


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
        "description": "在作品中的重要地位：核心空间。\n主要出现的情节：关键行动。\n现实地标介绍：真实地点。",
        "transit_text": "",
        "landmark_kind": "作品场景",
        "source_url": "https://example.org/seed-source",
        "source_publisher": "示例文旅局",
        "source_title": "示例来源",
        "source_type": "official",
        "accessed_at": "2026-08-10T09:00:00+08:00",
        "license_note": "",
        "claim_scope": "work_association",
    }
    row.update(overrides)
    return row


def seed_csv_bytes(rows) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=EXPECTED_COLUMNS, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def import_seed(db_session) -> int:
    result = LandmarkImportService(db_session).import_csv(seed_csv_bytes([entry_row()]))
    assert not result.failures
    return result.imported_landmark_ids[0]


def test_write_attributions_creates_row_for_github_username(db_session):
    landmark_id = import_seed(db_session)
    records = [
        {
            "file": "game/example-game--example-building.csv",
            "contributor": "octocat",
            "ip_type": "game",
            "work_title": "示例游戏",
            "landmark_name": "示例古建",
        }
    ]

    created = _write_attributions(db_session, records)

    assert created == 1
    contribution = db_session.scalar(
        select(LandmarkContribution).where(LandmarkContribution.landmark_id == landmark_id)
    )
    assert contribution is not None
    assert contribution.contributor_name == "octocat"
    assert contribution.contributor_user_id is None


def test_write_attributions_is_idempotent(db_session):
    import_seed(db_session)
    records = [
        {
            "file": "game/example-game--example-building.csv",
            "contributor": "octocat",
            "ip_type": "game",
            "work_title": "示例游戏",
            "landmark_name": "示例古建",
        }
    ]

    assert _write_attributions(db_session, records) == 1
    assert _write_attributions(db_session, records) == 0

    contributions = db_session.scalars(select(LandmarkContribution)).all()
    assert len(contributions) == 1


def test_write_attributions_skips_missing_landmark_and_empty_username(db_session):
    import_seed(db_session)
    records = [
        {"contributor": "octocat", "ip_type": "game", "work_title": "不存在的作品", "landmark_name": "不存在地标"},
        {"contributor": "", "ip_type": "game", "work_title": "示例游戏", "landmark_name": "示例古建"},
        {"contributor": "  ", "ip_type": "game", "work_title": "示例游戏", "landmark_name": "示例古建"},
    ]

    created = _write_attributions(db_session, records)

    assert created == 0
    assert db_session.scalars(select(LandmarkContribution)).all() == []


def test_load_attribution_manifests_collects_all_records(tmp_path):
    archive = tmp_path / "archive"
    day1 = archive / "2026-08-17"
    day1.mkdir(parents=True)
    day1.joinpath("manifest.json").write_text(
        json.dumps({"imports": [{"file": "a.csv", "contributor": "octo"}]}), encoding="utf-8"
    )
    day2 = archive / "2026-08-18"
    day2.mkdir(parents=True)
    day2.joinpath("manifest.json").write_text(
        json.dumps({"imports": [{"file": "b.csv", "contributor": "hub"}]}), encoding="utf-8"
    )

    records = _load_attribution_manifests(archive)

    assert [record["contributor"] for record in records] == ["octo", "hub"]


def test_load_attribution_manifests_handles_missing_or_corrupt(tmp_path):
    assert _load_attribution_manifests(tmp_path / "no-such-archive") == []

    archive = tmp_path / "archive"
    archive.mkdir()
    archive.joinpath("manifest.json").write_text("{broken", encoding="utf-8")

    assert _load_attribution_manifests(archive) == []
