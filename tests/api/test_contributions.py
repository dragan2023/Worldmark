from app.core.auth import create_access_token
from app.models.contribution import LandmarkContribution
from app.models.enums import MembershipTier, VerificationStatus
from app.models.landmark import Landmark
from app.services.review import LandmarkReviewService
from tests.factories import create_member


def contribution_payload() -> dict[str, str]:
    return {
        "contributor_name": "李明",
        "ip_type": "literature",
        "work_title": "测试作品",
        "landmark_name": "测试地标",
        "country_code": "CN",
        "country_name": "中国",
        "province_name": "北京市",
        "city_name": "北京市",
        "normalized_address": "北京市东城区测试街 1 号",
        "description": "在作品中的重要地位：该地点是作品的核心空间。\n主要出现的情节：主角在此展开关键行动。\n现实地标介绍：这里是可定位的真实地点。",
        "source_url": "https://example.org/community-source",
        "source_title": "共创者提供的来源",
    }


def test_public_contribution_creates_attributed_candidate(client, db_session):
    response = client.post("/api/v1/contributions/landmarks", json=contribution_payload())

    assert response.status_code == 201
    body = response.json()
    contribution = db_session.get(LandmarkContribution, body["contribution_id"])
    landmark = db_session.get(Landmark, body["landmark_id"])
    assert contribution.contributor_name == "李明"
    assert contribution.contributor_user_id is None
    assert contribution.landmark_id == landmark.id
    assert landmark.verification_status == VerificationStatus.CANDIDATE


def test_logged_in_contribution_binds_user_and_displays_attribution_after_publish(client, db_session):
    member = create_member(db_session, MembershipTier.LITE)
    response = client.post(
        "/api/v1/contributions/landmarks",
        json=contribution_payload() | {"landmark_name": "已发布测试地标"},
        headers={"Authorization": f"Bearer {create_access_token(member.id)}"},
    )

    assert response.status_code == 201
    landmark_id = response.json()["landmark_id"]
    contribution = db_session.get(LandmarkContribution, response.json()["contribution_id"])
    assert contribution.contributor_user_id == member.id
    reviewer = LandmarkReviewService(db_session)
    reviewer.review(landmark_id, VerificationStatus.VERIFIED, "来源与条目内容可核验。", "审核员")
    reviewer.publish(landmark_id)

    detail = client.get(f"/landmarks/{landmark_id}")
    assert detail.status_code == 200
    assert "共创者" in detail.text
    assert "李明" in detail.text


def test_contribution_requires_three_part_description(client):
    response = client.post("/api/v1/contributions/landmarks", json=contribution_payload() | {"description": "不符合结构的简介"})

    assert response.status_code == 422
