from datetime import UTC, datetime

from app.models.landmark import Landmark
from app.services.data_quality import LandmarkDataQualityService
from app.services.import_landmarks import LandmarkImportService


CSV = (
    "ip_type,work_title,landmark_name,country_code,country_name,normalized_address,description,source_url,source_type,accessed_at\n"
    "screen,示例剧集,示例地点,CN,中国,示例地址,原创简介,https://example.org/source,official,2026-08-10T09:00:00+08:00\n"
)


def test_quality_check_blocks_published_unverified_landmark(db_session):
    imported = LandmarkImportService(db_session).import_csv(CSV.encode())
    landmark = db_session.get(Landmark, imported.imported_landmark_ids[0])
    landmark.published_at = datetime.now(UTC)
    db_session.commit()

    issues = LandmarkDataQualityService(db_session).scan_published()

    assert {(issue.landmark_id, issue.code) for issue in issues} == {(landmark.id, "published_unverified")}
