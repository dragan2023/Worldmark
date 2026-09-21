"""M5：管理员用户管理 + 条目修改/下架/软删。"""

from app.core.auth import create_access_token
from app.models.enums import MembershipTier, UserRole
from tests.factories import create_admin, create_landmark, create_member


def _admin_headers(db_session):
    admin = create_admin(db_session)
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(admin.id)}"}, admin


def _member_headers(db_session, role=UserRole.LEVEL2.value):
    member = create_member(db_session, MembershipTier.FREE, role=role)
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(member.id)}"}


# ---------------------------------------------------------------- 用户管理


def test_user_management_requires_admin(client, db_session):
    headers = _member_headers(db_session)
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 401
    assert client.get("/api/v1/admin/users").status_code == 401


def test_admin_can_list_and_search_users(client, db_session):
    headers, admin = _admin_headers(db_session)
    create_member(db_session, MembershipTier.FREE)
    db_session.commit()

    body = client.get("/api/v1/admin/users", headers=headers).json()
    assert body["total"] >= 2
    assert all({"email", "role", "status", "tier"} <= set(item) for item in body["items"])

    searched = client.get("/api/v1/admin/users?q=dev", headers=headers).json()
    assert all("dev" in item["username"] or "dev" in item["email"] for item in searched["items"])


def test_admin_can_change_role_and_ban(client, db_session):
    headers, admin = _admin_headers(db_session)
    member = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    db_session.commit()

    promoted = client.patch(
        f"/api/v1/admin/users/{member.id}", json={"role": "level1"}, headers=headers
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "level1"

    banned = client.patch(f"/api/v1/admin/users/{member.id}", json={"status": "banned"}, headers=headers)
    assert banned.json()["status"] == "banned"

    # 被封禁用户的 token 立即失效
    rejected = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {create_access_token(member.id)}"})
    assert rejected.status_code == 403


def test_admin_cannot_modify_self_role_or_ban_self(client, db_session):
    headers, admin = _admin_headers(db_session)

    self_role = client.patch(f"/api/v1/admin/users/{admin.id}", json={"role": "level2"}, headers=headers)
    assert self_role.status_code == 422

    self_ban = client.patch(f"/api/v1/admin/users/{admin.id}", json={"status": "banned"}, headers=headers)
    assert self_ban.status_code == 422

    self_delete = client.delete(f"/api/v1/admin/users/{admin.id}", headers=headers)
    assert self_delete.status_code == 422


def test_delete_user_bans_but_keeps_row(client, db_session):
    headers, admin = _admin_headers(db_session)
    member = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    db_session.commit()

    deleted = client.delete(f"/api/v1/admin/users/{member.id}", headers=headers)
    assert deleted.json()["deleted"] is True

    from app.models.user import User

    db_session.expire_all()  # 另一会话提交的变更需要过期缓存
    assert db_session.get(User, member.id) is not None  # 软删：行仍在
    assert db_session.get(User, member.id).status == "banned"


def test_invalid_status_rejected(client, db_session):
    headers, admin = _admin_headers(db_session)
    member = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    db_session.commit()

    bad_status = client.patch(f"/api/v1/admin/users/{member.id}", json={"status": "paused"}, headers=headers)
    assert bad_status.status_code == 422


# ---------------------------------------------------------------- 条目管理


def test_admin_can_update_landmark_fields(client, db_session):
    headers, _ = _admin_headers(db_session)
    landmark = create_landmark(db_session, landmark_name="旧名称")
    db_session.commit()

    updated = client.patch(
        f"/api/v1/admin/landmarks/{landmark.id}",
        json={"name": "新名称", "transit_text": "地铁 2 号线"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["changed"] == ["name", "transit_text"]
    db_session.refresh(landmark)
    assert landmark.name == "新名称"


def test_admin_can_unpublish_landmark(client, db_session):
    headers, _ = _admin_headers(db_session)
    landmark = create_landmark(db_session, published=True)
    db_session.commit()
    assert landmark.published_at is not None

    response = client.post(f"/api/v1/admin/landmarks/{landmark.id}/unpublish", headers=headers)
    assert response.json()["published"] is False
    db_session.refresh(landmark)
    assert landmark.published_at is None


def test_soft_delete_hides_landmark_and_restore_recovers(client, db_session):
    headers, _ = _admin_headers(db_session)
    landmark = create_landmark(db_session, published=True, landmark_name="待删地标")
    db_session.commit()
    landmark_id = landmark.id

    deleted = client.delete(f"/api/v1/admin/landmarks/{landmark_id}", headers=headers)
    assert deleted.json()["deleted"] is True
    db_session.expire_all()

    # 普通查询自动过滤
    hidden = client.get(f"/api/v1/landmarks/{landmark_id}")
    assert hidden.status_code == 404

    # 管理员可见（include_deleted）
    admin_view = client.get(f"/api/v1/admin/landmarks/{landmark_id}", headers=headers)
    assert admin_view.status_code == 200
    assert admin_view.json()["deleted_at"] is not None

    restored = client.post(f"/api/v1/admin/landmarks/{landmark_id}/restore", headers=headers)
    assert restored.json()["deleted"] is False
    db_session.expire_all()
    assert client.get(f"/api/v1/landmarks/{landmark_id}").status_code == 200
