"""管理后台：地标管理列表筛选 + /admin 页面门禁。"""

import pytest

from app.core.auth import CurrentMember, get_current_member
from app.models.enums import MembershipTier, UserRole, VerificationStatus
from tests.factories import create_admin, create_landmark, create_member


@pytest.fixture
def admin_client(app, db_session, client):
    admin = create_admin(db_session)
    db_session.commit()
    app.dependency_overrides[get_current_member] = lambda: CurrentMember(
        user_id=admin.id, tier=MembershipTier.FREE, role=UserRole.ADMIN
    )
    yield client
    app.dependency_overrides.pop(get_current_member, None)


def _headers(db_session, role=UserRole.LEVEL2.value):
    member = create_member(db_session, MembershipTier.FREE, role=role)
    db_session.commit()
    from app.core.auth import create_access_token

    return {"Authorization": f"Bearer {create_access_token(member.id)}"}


def test_landmark_list_filters_by_status(admin_client, db_session):
    pending = create_landmark(db_session, published=False, landmark_name="候选地标")
    verified = create_landmark(db_session, landmark_name="核验地标")
    db_session.commit()
    assert pending.verification_status == VerificationStatus.CANDIDATE

    pending_list = admin_client.get("/api/v1/admin/landmarks?status=pending").json()
    assert [i["name"] for i in pending_list["items"]] == ["候选地标"]

    verified_list = admin_client.get("/api/v1/admin/landmarks?status=verified").json()
    assert [i["name"] for i in verified_list["items"]] == ["核验地标"]

    all_list = admin_client.get("/api/v1/admin/landmarks?status=all").json()
    assert all_list["total"] >= 2


def test_landmark_list_shows_deleted_in_trash(admin_client, db_session):
    landmark = create_landmark(db_session, landmark_name="将删地标")
    db_session.commit()
    admin_client.delete(f"/api/v1/admin/landmarks/{landmark.id}")

    pending_list = admin_client.get("/api/v1/admin/landmarks?status=pending").json()
    assert all(i["name"] != "将删地标" for i in pending_list["items"])

    trash = admin_client.get("/api/v1/admin/landmarks?status=deleted").json()
    assert [i["name"] for i in trash["items"]] == ["将删地标"]
    assert trash["items"][0]["deleted"] is True


def test_landmark_list_requires_admin(client, db_session):
    headers = _headers(db_session)
    assert client.get("/api/v1/admin/landmarks?status=all", headers=headers).status_code == 401
    assert client.get("/api/v1/admin/landmarks?status=all").status_code == 401


def test_landmark_list_includes_work_and_region(admin_client, db_session):
    create_landmark(db_session, landmark_name="完整条目")
    db_session.commit()

    body = admin_client.get("/api/v1/admin/landmarks?status=all").json()
    item = next(i for i in body["items"] if i["name"] == "完整条目")
    assert item["work_title"]
    assert item["ip_type"]


def test_landmark_detail_includes_full_content_for_review(admin_client, db_session):
    landmark = create_landmark(db_session, published=False, landmark_name="审核详情地标")
    db_session.commit()

    body = admin_client.get(f"/api/v1/admin/landmarks/{landmark.id}").json()
    assert body["name"] == "审核详情地标"
    assert body["description"]
    assert body["work_title"] == "黑神话：悟空"
    assert body["ip_type"] == "game"
    assert body["address"]
    assert len(body["sources"]) == 1
    assert body["sources"][0]["url"].startswith("https://")
    assert body["photos"] == []  # 无相册


def test_landmark_detail_includes_album_photos(app, db_session, client):
    from app.api.album import get_album_editor

    class StubEditor:
        def editor_snapshot(self, landmark_id):
            return {
                "published": [
                    {"kind": "published", "file": "a/b.jpg", "url": "/contributions/landmark-albums/images/a/b.jpg",
                     "alt": "正式", "caption": "山门", "credit": "维基", "license": "CC BY-SA", "source_url": "https://commons.example/a"},
                ],
                "staged": [
                    {"kind": "upload", "url": "/staging/landmark-albums/9/x.jpg", "alt": "上传", "caption": None,
                     "credit": None, "license": None, "source_url": None},
                    {"kind": "ai", "url": "/staging/landmark-albums/9/y.jpg", "alt": "AI", "caption": None,
                     "credit": None, "license": "Public domain", "source_url": "https://commons.example/y"},
                ],
            }

    admin = create_admin(db_session)
    db_session.commit()
    app.dependency_overrides[get_current_member] = lambda: CurrentMember(
        user_id=admin.id, tier=MembershipTier.FREE, role=UserRole.ADMIN
    )
    app.dependency_overrides[get_album_editor] = lambda: StubEditor()

    landmark = create_landmark(db_session, published=False, landmark_name="有图地标")
    db_session.commit()
    body = client.get(f"/api/v1/admin/landmarks/{landmark.id}").json()

    kinds = [p["kind"] for p in body["photos"]]
    assert kinds == ["published", "upload", "ai"]
    assert body["photos"][0]["url"].startswith("/contributions/landmark-albums/images/")
    assert body["photos"][1]["kind_label"] == "用户上传"
    assert body["photos"][2]["kind_label"] == "AI 找图"

    app.dependency_overrides.pop(get_current_member, None)
    app.dependency_overrides.pop(get_album_editor, None)


def test_landmark_detail_requires_admin(client, db_session):
    headers = _headers(db_session)
    assert client.get("/api/v1/admin/landmarks/1", headers=headers).status_code == 401


def test_review_endpoint_accepts_lowercase_dashboard_payload(admin_client, db_session):
    """管理后台以小写枚举值提交审核（回归：大写会被 422 拒绝导致操作无效）。"""
    landmark = create_landmark(db_session, published=False, landmark_name="待审核条目")
    db_session.commit()

    response = admin_client.post(
        f"/api/v1/admin/landmarks/{landmark.id}/review",
        json={"decision": "verified", "reason": "内容核验通过", "reviewer_name": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["verification_status"] == "verified"

    db_session.refresh(landmark)
    assert landmark.verification_status == VerificationStatus.VERIFIED


def test_review_rejects_uppercase_enum_name(admin_client, db_session):
    landmark = create_landmark(db_session, published=False, landmark_name="大写回归")
    db_session.commit()
    response = admin_client.post(
        f"/api/v1/admin/landmarks/{landmark.id}/review",
        json={"decision": "VERIFIED", "reason": "r", "reviewer_name": "admin"},
    )
    assert response.status_code == 422


def test_dashboard_page_admin_only(app, db_session, client):
    # 匿名 → 登录页（不跟随重定向）
    anon = client.get("/admin", follow_redirects=False)
    assert anon.status_code == 302 and "/login" in anon.headers["location"]

    # 普通用户 → 首页
    member = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    db_session.commit()
    app.dependency_overrides[get_current_member] = lambda: CurrentMember(
        user_id=member.id, tier=MembershipTier.FREE, role=UserRole.LEVEL2
    )
    member_resp = client.get("/admin", follow_redirects=False)
    assert member_resp.status_code == 302 and member_resp.headers["location"] == "/"
    app.dependency_overrides.pop(get_current_member, None)

    # 管理员 → 200
    admin = create_admin(db_session)
    db_session.commit()
    app.dependency_overrides[get_current_member] = lambda: CurrentMember(
        user_id=admin.id, tier=MembershipTier.FREE, role=UserRole.ADMIN
    )
    page = client.get("/admin", follow_redirects=False)
    assert page.status_code == 200
    assert "地标审核" in page.text
    app.dependency_overrides.pop(get_current_member, None)


def test_old_users_page_redirects_to_dashboard(app, db_session, client):
    admin = create_admin(db_session)
    db_session.commit()
    app.dependency_overrides[get_current_member] = lambda: CurrentMember(
        user_id=admin.id, tier=MembershipTier.FREE, role=UserRole.ADMIN
    )
    response = client.get("/admin/users", follow_redirects=False)
    assert response.status_code == 302 and response.headers["location"].endswith("/admin")
    app.dependency_overrides.pop(get_current_member, None)
