"""权限矩阵：关键端点 × 匿名/二级/一级/管理员 逐格断言。"""

import pytest

from app.core.auth import create_access_token
from app.models.enums import MembershipTier, UserRole
from tests.factories import create_member


def _auth_headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _auth_headers_for(db_session, role: str) -> dict[str, str]:
    user = create_member(db_session, MembershipTier.FREE, role=role)
    db_session.commit()
    return _auth_headers(user)


def test_itinerary_endpoints_role_matrix(client, app, db_session):
    """个性化行程：匿名 401 / 二级 403 / 一级、管理员放行（到 422 参数校验）。"""
    url = "/api/v1/itineraries"

    assert client.post(url, json={}).status_code == 401

    level2 = _auth_headers_for(db_session, UserRole.LEVEL2.value)
    response = client.post(url, json={}, headers=level2)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "role_required"
    assert response.json()["detail"]["required"] == "level1"

    for role in (UserRole.LEVEL1, UserRole.ADMIN):
        headers = _auth_headers_for(db_session, role.value)
        passed = client.post(url, json={}, headers=headers)
        assert passed.status_code != 403, role
        assert passed.status_code != 401, role


def test_admin_endpoints_accept_admin_role_without_static_token(client, app, db_session):
    admin = _auth_headers_for(db_session, UserRole.ADMIN.value)
    assert client.get("/api/v1/admin/data-quality", headers=admin).status_code == 200


def test_admin_endpoints_reject_non_admin_roles(client, app, db_session):
    for role in (UserRole.LEVEL1, UserRole.LEVEL2):
        headers = _auth_headers_for(db_session, role.value)
        assert client.get("/api/v1/admin/data-quality", headers=headers).status_code == 401
    assert client.get("/api/v1/admin/data-quality").status_code == 401


def test_admin_endpoints_without_any_configuration(client, app, db_session, monkeypatch):
    """过渡期：既无 admin 角色 token 也未配置静态令牌 → 401。"""

    class FakeSettings:
        admin_api_token = None
        dev_bypass_auth = False
        is_production = False

    monkeypatch.setattr("app.core.config.get_settings", lambda: FakeSettings())
    response = client.get("/api/v1/admin/data-quality", headers={"X-Admin-Token": "whatever"})
    assert response.status_code in (401, 503)


def test_intake_requires_member_only(client, app, db_session):
    """一键入库：二级即可（不要求一级）；无 LLM 配置时 503 而非 401/403。"""
    level2 = _auth_headers_for(db_session, UserRole.LEVEL2.value)
    response = client.post("/api/v1/agent/landmarks/intake", json={"input": "测试 地标"}, headers=level2)
    assert response.status_code not in (401, 403)

    anonymous = client.post("/api/v1/agent/landmarks/intake", json={"input": "测试 地标"})
    assert anonymous.status_code == 401


@pytest.mark.parametrize(
    ("role", "feature", "expected"),
    [
        (UserRole.LEVEL2, "can_intake", True),
        (UserRole.LEVEL2, "can_generate_itinerary", False),
        (UserRole.LEVEL1, "can_generate_itinerary", True),
        (UserRole.LEVEL1, "can_manage_users", False),
        (UserRole.ADMIN, "can_manage_users", True),
        (UserRole.ADMIN, "can_manage_system_keys", True),
    ],
)
def test_role_matrix_cells(role, feature, expected):
    from app.services.permissions import permissions_for_role

    assert getattr(permissions_for_role(role), feature) is expected
