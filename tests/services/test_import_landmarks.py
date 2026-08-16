from app.models.enums import VerificationStatus
from app.models.landmark import Landmark
from app.services.import_landmarks import LandmarkImportService
from app.services.review import LandmarkReviewService


CSV_HEADER = (
    "ip_type,work_title,aliases,landmark_name,country_code,country_name,province_name,city_name,district_name,"
    "normalized_address,latitude,longitude,description,transit_text,landmark_kind,source_url,source_publisher,"
    "source_title,source_type,accessed_at,license_note,claim_scope\n"
)
CSV_ROW = (
    "game,示例游戏,,示例古建,CN,中国,山西省,大同市,,示例地址,39.9,113.3,原创地点简介,"
    "交通信息更新于 2026-08-10,古建,https://example.org/source,示例文旅局,示例来源,official,"
    "2026-08-10T09:00:00+08:00,,work_association\n"
)


def test_imports_a_candidate_with_source_and_location(db_session):
    result = LandmarkImportService(db_session).import_csv((CSV_HEADER + CSV_ROW).encode())

    assert result.failures == ()
    assert len(result.imported_landmark_ids) == 1
    landmark = db_session.get(Landmark, result.imported_landmark_ids[0])
    assert landmark.verification_status == VerificationStatus.CANDIDATE
    assert landmark.location.city_name == "大同市"
    assert landmark.sources[0].source.url == "https://example.org/source"


def test_rejects_invalid_source_without_partially_importing_rows(db_session):
    invalid_row = CSV_ROW.replace("https://example.org/source", "not-a-url")
    result = LandmarkImportService(db_session).import_csv((CSV_HEADER + invalid_row).encode())

    assert result.imported_landmark_ids == ()
    assert result.failures[0].row_number == 2
    assert db_session.query(Landmark).count() == 0


def test_accepts_blank_optional_coordinates(db_session):
    row_without_coordinates = CSV_ROW.replace("39.9,113.3", ",")

    result = LandmarkImportService(db_session).import_csv((CSV_HEADER + row_without_coordinates).encode())

    assert result.failures == ()
    landmark = db_session.get(Landmark, result.imported_landmark_ids[0])
    assert landmark.location.latitude is None
    assert landmark.location.longitude is None


def test_verified_candidate_can_be_published(db_session):
    imported = LandmarkImportService(db_session).import_csv((CSV_HEADER + CSV_ROW).encode())
    landmark_id = imported.imported_landmark_ids[0]
    review_service = LandmarkReviewService(db_session)

    reviewed = review_service.review(landmark_id, VerificationStatus.VERIFIED, "来源和地址已核验", "审核员")
    published = review_service.publish(landmark_id)

    assert reviewed.verification_status == VerificationStatus.VERIFIED
    assert published.published_at is not None
    assert published.ip_work.status.value == "published"
