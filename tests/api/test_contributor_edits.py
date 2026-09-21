"""贡献者修改自己地标：内容 + 相册；每次修改进入重新审核。管理员即时生效。"""

import pytest

from app.core.auth import CurrentMember, create_access_token, get_current_member
from app.models.enums import MembershipTier, UserRole, VerificationStatus
from app.models.contribution import LandmarkContribution
from tests.factories import create_admin, create_landmark, create_member


@pytest.fixture
def owned_landmark(db_session):
    """贡献者拥有的已发布地标。"""
    contributor = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    landmark = create_landmark(db_session, published=True, landmark_name="我提交的地标")
    db_session.add(LandmarkContribution(
        landmark_id=landmark.id, contributor_name=contributor.username, contributor_user_id=contributor.id,
    ))
    db_session.commit()
    return contributor, landmark


def _headers(db_session, user):
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_contributor_edit_puts_landmark_back_into_review(client, db_session, owned_landmark):
    contributor, landmark = owned_landmark
    headers = _headers(db_session, contributor)

    response = client.patch(
        f"/api/v1/landmarks/{landmark.id}/content",
        json={"description": "贡献者更新后的简介"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["review_required"] is True

    db_session.expire_all()
    assert landmark.verification_status == VerificationStatus.CANDIDATE
    assert landmark.published_at is None  # 重新审核通过前暂时下架


def test_admin_edit_via_contributor_endpoint_is_instant(client, db_session, owned_landmark):
    admin = create_admin(db_session)
    _, landmark = owned_landmark
    headers = _headers(db_session, admin)

    response = client.patch(
        f"/api/v1/landmarks/{landmark.id}/content",
        json={"description": "管理员直接修正"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["review_required"] is False

    db_session.expire_all()
    assert landmark.verification_status == VerificationStatus.VERIFIED
    assert landmark.published_at is not None  # 即时生效，不下架


def test_non_contributor_member_cannot_edit(client, db_session, owned_landmark):
    other = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    _, landmark = owned_landmark
    headers = _headers(db_session, other)

    response = client.patch(
        f"/api/v1/landmarks/{landmark.id}/content",
        json={"description": "路人乱改"},
        headers=headers,
    )
    assert response.status_code == 403

    db_session.expire_all()
    assert landmark.verification_status == VerificationStatus.VERIFIED  # 内容未被改动


def test_anonymous_cannot_edit(client, db_session, owned_landmark):
    _, landmark = owned_landmark
    assert client.patch(
        f"/api/v1/landmarks/{landmark.id}/content", json={"description": "匿名"}
    ).status_code == 401


def test_album_endpoints_require_contributor_or_admin(client, app, db_session, owned_landmark):
    from app.api.album import get_album_editor

    class StubEditor:
        def editor_snapshot(self, landmark_id):
            return {"published": [], "staged": [], "landmark": {}}

        def submit(self, landmark_id, photos):
            return {"added_count": 1, "removed_count": 0, "published_count": 1}

    contributor, landmark = owned_landmark
    other = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    admin = create_admin(db_session)

    app.dependency_overrides[get_album_editor] = lambda: StubEditor()

    # 路人 → 403
    other_headers = _headers(db_session, other)
    assert client.get(f"/api/v1/landmarks/{landmark.id}/album/editor", headers=other_headers).status_code == 403
    assert client.post(
        f"/api/v1/landmarks/{landmark.id}/album/submit",
        json={"photos": [{"kind": "upload", "file": "x.jpg", "alt": "x"}]},
        headers=other_headers,
    ).status_code == 403

    # 贡献者 → 200，且提交触发重新审核
    contributor_headers = _headers(db_session, contributor)
    assert client.get(f"/api/v1/landmarks/{landmark.id}/album/editor", headers=contributor_headers).status_code == 200
    submit = client.post(
        f"/api/v1/landmarks/{landmark.id}/album/submit",
        json={"photos": [{"kind": "upload", "file": "x.jpg", "alt": "x"}]},
        headers=contributor_headers,
    )
    assert submit.status_code == 200
    assert "重新审核" in submit.json()["review_note"]
    db_session.expire_all()
    assert landmark.verification_status == VerificationStatus.CANDIDATE
    assert landmark.published_at is None

    # 管理员提交 → 即时生效（不改变状态）
    from datetime import UTC, datetime

    landmark.verification_status = VerificationStatus.VERIFIED
    landmark.published_at = datetime.now(UTC)
    db_session.commit()
    admin_headers = _headers(db_session, admin)
    submit2 = client.post(
        f"/api/v1/landmarks/{landmark.id}/album/submit",
        json={"photos": [{"kind": "upload", "file": "y.jpg", "alt": "y"}]},
        headers=admin_headers,
    )
    assert submit2.status_code == 200
    assert "review_note" not in submit2.json()
    db_session.expire_all()
    assert landmark.verification_status == VerificationStatus.VERIFIED
    assert landmark.published_at is not None

    app.dependency_overrides.pop(get_album_editor, None)


def test_contributor_can_read_own_content_for_editing(client, db_session, owned_landmark):
    contributor, landmark = owned_landmark
    headers = _headers(db_session, contributor)

    body = client.get(f"/api/v1/landmarks/{landmark.id}/content", headers=headers).json()
    assert body["name"] == "我提交的地标"
    assert body["description"]
    assert body["published"] is True
    assert body["is_admin"] is False


def test_content_read_requires_contributor(client, db_session, owned_landmark):
    other = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    _, landmark = owned_landmark
    headers = _headers(db_session, other)
    assert client.get(f"/api/v1/landmarks/{landmark.id}/content", headers=headers).status_code == 403
    assert client.get(f"/api/v1/landmarks/{landmark.id}/content").status_code == 401


def test_reviewer_can_reapprove_after_contributor_edit(client, db_session, owned_landmark):
    """贡献者修改后，管理员走 审核通过 → 发布 重新上架。"""
    from app.services.review import LandmarkReviewService

    contributor, landmark = owned_landmark
    headers = _headers(db_session, contributor)
    client.patch(
        f"/api/v1/landmarks/{landmark.id}/content",
        json={"description": "修改后的简介"},
        headers=headers,
    )
    db_session.expire_all()
    assert landmark.published_at is None

    LandmarkReviewService(db_session).review(
        landmark.id, VerificationStatus.VERIFIED, "重新核验通过", "admin"
    )
    LandmarkReviewService(db_session).publish(landmark.id)

    db_session.expire_all()
    assert landmark.verification_status == VerificationStatus.VERIFIED
    assert landmark.published_at is not None
