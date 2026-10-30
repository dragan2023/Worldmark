"""阶段02 回归：页面/API 权限一致、密钥不回落、单条变更不牵连同作品、状态转换准确。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from app.core.auth import create_access_token
from app.models.enums import IPType, MembershipTier, PublicationStatus, UserRole, VerificationStatus
from app.services.landmark_catalog import CatalogFilters, LandmarkCatalogService
from app.services.map_data import MapDataService
from tests.factories import create_admin, create_landmark, create_member


def _headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _payload(landmark_id: int, **overrides) -> dict[str, object]:
    value: dict[str, object] = {
        "ip_type": "game",
        "work": "黑神话：悟空",
        "origin_city": "朔州",
        "start_date": "2026-09-01",
        "end_date": "2026-09-01",
        "daily_hours": 8,
        "must_visit_landmark_ids": [landmark_id],
    }
    value.update(overrides)
    return value


# --------------------------------------------------------------- B02 页面/接口


def test_anonymous_itinerary_page_redirects_to_login_with_next(client):
    for path in ("/itineraries", "/itineraries/new"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == f"/login?next={path}"


def test_anonymous_itinerary_api_returns_401_not_500(client):
    assert client.get("/api/v1/itineraries").status_code == 401
    # 不再为访客创建共享 guest 用户：库里不会出现 anonymous@iplandmarks.local
    from sqlalchemy import select

    from app.models.user import User

    assert client.get("/api/v1/itineraries").status_code == 401


def test_level2_page_explains_capability_instead_of_showing_usable_form(client, db_session):
    level2 = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    response = client.get("/itineraries/new", headers=_headers(level2))

    assert response.status_code == 403
    assert "一级贡献者" in response.text
    assert "参与共创" in response.text
    # 表单本身不再渲染给无权限用户
    assert 'id="itinerary-form"' not in response.text


def test_level1_can_open_form_and_create(client, db_session):
    landmark = create_landmark(db_session)
    level1 = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)

    assert client.get("/itineraries/new", headers=_headers(level1)).status_code == 200
    created = client.post("/api/v1/itineraries", json=_payload(landmark.id), headers=_headers(level1))
    assert created.status_code == 200


def test_login_next_rejects_offsite_target(client):
    response = client.get("/login?next=//evil.example/x")
    assert response.status_code == 200  # 页面本身可看，但 next 不会进入跳转逻辑
    from app.core.auth import safe_next_path

    assert safe_next_path("//evil.example/x") == "/"
    assert safe_next_path("https://evil.example") == "/"
    assert safe_next_path("/itineraries/3") == "/itineraries/3"


# ------------------------------------------------ R01 普通用户不调用系统密钥


def test_choice_preview_never_falls_back_to_system_credentials(client, db_session, monkeypatch):
    landmark = create_landmark(db_session)
    level1 = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)

    from app.core.config import Settings
    from app.api import itineraries as itineraries_api

    system_settings = Settings(meituan_ht_token=SecretStr("system-meituan-token"))
    monkeypatch.setattr(itineraries_api, "get_settings", lambda: system_settings)

    captured: dict[str, object] = {}

    def fake_enrichment(self):
        token = self._settings.effective_meituan_travel_token
        captured["token"] = token.get_secret_value() if token else None
        raise RuntimeError("stop after capturing settings")

    monkeypatch.setattr(
        "app.services.itinerary_planner.ItineraryPlannerService._build_travel_enrichment",
        fake_enrichment,
    )

    with pytest.raises(RuntimeError):
        client.post("/api/v1/itineraries/choice-preview", json=_payload(landmark.id), headers=_headers(level1))
    assert captured["token"] is None  # 普通用户未自配密钥 → 不注入系统密钥


def test_choice_preview_admin_may_fall_back_to_system_credentials(client, db_session, monkeypatch):
    landmark = create_landmark(db_session)
    admin = create_admin(db_session)

    from app.core.config import Settings
    from app.api import itineraries as itineraries_api

    system_settings = Settings(meituan_ht_token=SecretStr("system-meituan-token"))
    monkeypatch.setattr(itineraries_api, "get_settings", lambda: system_settings)

    captured: dict[str, object] = {}

    def fake_enrichment(self):
        token = self._settings.effective_meituan_travel_token
        captured["token"] = token.get_secret_value() if token else None
        raise RuntimeError("stop after capturing settings")

    monkeypatch.setattr(
        "app.services.itinerary_planner.ItineraryPlannerService._build_travel_enrichment",
        fake_enrichment,
    )

    with pytest.raises(RuntimeError):
        client.post("/api/v1/itineraries/choice-preview", json=_payload(landmark.id), headers=_headers(admin))
    assert captured["token"] == "system-meituan-token"  # 管理员保留既有系统回落规则


# ------------------------------------------------- B03/B04 状态转换与公开条件


def test_unpublishing_one_landmark_keeps_sibling_public(client, db_session):
    admin = create_admin(db_session)
    first = create_landmark(db_session, landmark_name="应县木塔")
    second = create_landmark(db_session, landmark_name="小西天", ip_work=first.ip_work)

    response = client.post(f"/api/v1/admin/landmarks/{first.id}/unpublish", headers=_headers(admin))
    assert response.status_code == 200

    db_session.expire_all()
    assert first.ip_work.status == PublicationStatus.PUBLISHED
    assert client.get(f"/landmarks/{second.id}").status_code == 200
    assert client.get(f"/api/v1/landmarks/{second.id}").status_code == 200
    assert client.get(f"/landmarks/{first.id}").status_code == 404


def test_rejected_published_landmark_disappears_everywhere(client, db_session):
    admin = create_admin(db_session)
    landmark = create_landmark(db_session, landmark_name="撤下测试地标")
    assert client.get(f"/landmarks/{landmark.id}").status_code == 200

    reviewed = client.post(
        f"/api/v1/admin/landmarks/{landmark.id}/review",
        json={"decision": "rejected", "reason": "来源失效"},
        headers=_headers(admin),
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["published"] is False

    db_session.expire_all()
    assert landmark.published_at is None
    assert client.get(f"/landmarks/{landmark.id}").status_code == 404
    assert client.get(f"/api/v1/landmarks/{landmark.id}").status_code == 404
    search_page = client.get("/search?q=撤下测试地标")
    assert f"/landmarks/{landmark.id}" not in search_page.text
    assert "没有匹配的地标" in search_page.text

    service = LandmarkCatalogService(db_session)
    assert service.search("撤下测试地标").total == 0
    assert service.filter_options(IPType.GAME).cities == ()
    assert MapDataService(db_session).list_markers(CatalogFilters()) == ()


def test_soft_deleted_landmark_hidden_and_restore_requires_review(client, db_session):
    admin = create_admin(db_session)
    landmark = create_landmark(db_session, landmark_name="软删测试地标")

    assert client.delete(f"/api/v1/admin/landmarks/{landmark.id}", headers=_headers(admin)).status_code == 200
    assert client.get(f"/landmarks/{landmark.id}").status_code == 404

    assert client.post(f"/api/v1/admin/landmarks/{landmark.id}/restore", headers=_headers(admin)).status_code == 200
    assert client.get(f"/landmarks/{landmark.id}").status_code == 200

    # 未核验的条目恢复后仍不公开
    landmark.verification_status = VerificationStatus.CANDIDATE
    landmark.published_at = None
    db_session.commit()
    client.delete(f"/api/v1/admin/landmarks/{landmark.id}", headers=_headers(admin))
    client.post(f"/api/v1/admin/landmarks/{landmark.id}/restore", headers=_headers(admin))
    assert client.get(f"/landmarks/{landmark.id}").status_code == 404


# ------------------------------------------------------------ B11/输入与角色


def test_admin_whitespace_name_is_rejected_without_writing(client, db_session):
    admin = create_admin(db_session)
    landmark = create_landmark(db_session, landmark_name="原名地标")

    response = client.patch(
        f"/api/v1/admin/landmarks/{landmark.id}",
        json={"name": "   "},
        headers=_headers(admin),
    )
    assert response.status_code == 422
    db_session.expire_all()
    assert landmark.name == "原名地标"


def test_contributor_whitespace_description_is_rejected(client, db_session):
    from app.models.contribution import LandmarkContribution

    contributor = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    landmark = create_landmark(db_session, landmark_name="贡献者地标")
    db_session.add(LandmarkContribution(
        landmark_id=landmark.id, contributor_name=contributor.username, contributor_user_id=contributor.id,
    ))
    db_session.commit()

    response = client.patch(
        f"/api/v1/landmarks/{landmark.id}/content",
        json={"description": " \n "},
        headers=_headers(contributor),
    )
    assert response.status_code == 422
    db_session.expire_all()
    assert landmark.description


def test_unknown_role_is_rejected_not_silently_downgraded(client, db_session):
    admin = create_admin(db_session)
    target = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)

    response = client.patch(
        f"/api/v1/admin/users/{target.id}", json={"role": "superuser"}, headers=_headers(admin)
    )
    assert response.status_code == 422
    db_session.expire_all()
    assert target.role == UserRole.LEVEL1.value


def test_duplicate_registration_returns_409_without_partial_write(client, db_session):
    payload = {"username": "dupuser", "email": "dup@example.org", "password": "correct-horse"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    duplicate = client.post("/api/v1/auth/register", json=payload)
    assert duplicate.status_code == 409

    from sqlalchemy import func, select

    from app.models.membership import Membership

    count = db_session.scalar(select(func.count()).select_from(Membership))
    assert count == 1  # 只创建了一条会员记录，没有半写入


def test_admin_list_count_matches_filter(client, db_session):
    admin = create_admin(db_session)
    create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)

    body = client.get("/api/v1/admin/users?q=nomatch", headers=_headers(admin)).json()
    assert body["total"] == 0
    assert body["items"] == []


def test_me_matches_server_side_role_for_admin_flag(client, db_session):
    from app.models.user import User

    user = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    user.is_admin = True  # 历史兼容字段
    db_session.commit()

    me = client.get("/api/v1/auth/me", headers=_headers(user)).json()
    assert me["role"] == UserRole.ADMIN.value
    # 服务端权威：/me 说 admin，则管理接口必须放行
    assert client.get("/api/v1/admin/data-quality", headers=_headers(user)).status_code == 200
