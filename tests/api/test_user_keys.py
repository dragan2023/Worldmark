"""M4：个人密钥 API + 密钥隔离解析 + 静态加密。"""

import pytest
from pydantic import SecretStr

from app.core import secret_box
from app.core.auth import create_access_token
from app.models.enums import MembershipTier, UserRole
from app.services.key_resolution import KeyResolutionService, PROVIDER_FIELDS
from tests.factories import create_admin, create_member

# ---------------------------------------------------------------- 静态加密


def test_secret_box_roundtrip_and_hint():
    token = secret_box.encrypt("sk-my-secret-key-123456")
    assert "sk-my-secret" not in token  # 密文不含明文片段
    assert secret_box.decrypt(token) == "sk-my-secret-key-123456"
    assert secret_box.key_hint("sk-1234567890abcdef") == "sk-1****cdef"
    assert secret_box.key_hint("short") == "****"


# ---------------------------------------------------------------- 密钥隔离解析


class _FakeMember:
    def __init__(self, user_id, role=UserRole.LEVEL2):
        self.user_id = user_id
        self.role = role
        self.tier = MembershipTier.FREE


def _base_settings():
    from app.core.config import Settings

    return Settings(
        _env_file=None,
        deepseek_api_key=SecretStr("sk-system-key"),
        amap_web_service_api_key=SecretStr("amap-system-key"),
    )


def test_regular_user_without_keys_gets_all_system_keys_blanked(db_session):
    member = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    db_session.commit()

    effective = KeyResolutionService(db_session).effective_settings(
        _FakeMember(member.id), _base_settings()
    )

    assert effective.deepseek_api_key is None
    assert effective.amap_web_service_api_key is None


def test_regular_user_uses_own_keys_only(db_session):
    member = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    db_session.commit()
    service = KeyResolutionService(db_session)
    service.set_key(member.id, "deepseek", "sk-user-own-key", verified=False)

    effective = service.effective_settings(_FakeMember(member.id), _base_settings())

    assert effective.deepseek_api_key.get_secret_value() == "sk-user-own-key"
    assert effective.amap_web_service_api_key is None  # 未自配的不回落


def test_admin_falls_back_to_system_keys(db_session):
    admin = create_admin(db_session)
    db_session.commit()

    effective = KeyResolutionService(db_session).effective_settings(
        _FakeMember(admin.id, role=UserRole.ADMIN), _base_settings()
    )

    assert effective.deepseek_api_key.get_secret_value() == "sk-system-key"


def test_admin_user_key_overrides_system(db_session):
    admin = create_admin(db_session)
    db_session.commit()
    service = KeyResolutionService(db_session)
    service.set_key(admin.id, "amap", "amap-user-key", verified=False)

    effective = service.effective_settings(_FakeMember(admin.id, role=UserRole.ADMIN), _base_settings())

    assert effective.amap_web_service_api_key.get_secret_value() == "amap-user-key"
    assert effective.deepseek_api_key.get_secret_value() == "sk-system-key"


def test_set_key_is_upsert_and_delete(db_session):
    member = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    db_session.commit()
    service = KeyResolutionService(db_session)

    first = service.set_key(member.id, "bocha", "sk-bocha-old", verified=False)
    second = service.set_key(member.id, "bocha", "sk-bocha-new", verified=True)
    assert first.id == second.id  # upsert 不重复建行
    assert service.user_key(member.id, "bocha") == "sk-bocha-new"
    assert second.verified_at is not None

    assert service.delete_key(member.id, "bocha") is True
    assert service.user_key(member.id, "bocha") is None


# ---------------------------------------------------------------- API


def _member_headers(db_session, role=UserRole.LEVEL2.value):
    member = create_member(db_session, MembershipTier.FREE, role=role)
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(member.id)}"}, member


def test_list_keys_requires_login(client):
    assert client.get("/api/v1/me/api-keys").status_code == 401


def test_list_keys_returns_catalog_without_plaintext(client, db_session):
    headers, member = _member_headers(db_session)
    KeyResolutionService(db_session).set_key(member.id, "deepseek", "sk-1234567890abcdef", verified=False)

    body = client.get("/api/v1/me/api-keys", headers=headers).json()

    providers = {item["provider"] for item in body["items"]}
    assert providers == set(PROVIDER_FIELDS.keys())
    deepseek = next(item for item in body["items"] if item["provider"] == "deepseek")
    assert deepseek["configured"] is True
    assert deepseek["key_hint"] == "sk-1****cdef"
    assert "sk-1234567890abcdef" not in str(body)


def test_put_key_rejects_unknown_provider_and_empty_value(client, db_session):
    headers, _ = _member_headers(db_session)
    assert client.put("/api/v1/me/api-keys/unknown", json={"value": "x" * 10}, headers=headers).status_code == 404
    assert client.put("/api/v1/me/api-keys/deepseek", json={"value": "", "verify": False}, headers=headers).status_code == 422


def test_put_key_without_verify_saves_masked(client, db_session):
    headers, _ = _member_headers(db_session)
    response = client.put(
        "/api/v1/me/api-keys/deepseek", json={"value": "sk-my-user-key-9876", "verify": False}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["key_hint"] == "sk-m****9876"
    assert body["verified"] is False


def test_delete_key_reports_missing(client, db_session):
    headers, _ = _member_headers(db_session)
    body = client.delete("/api/v1/me/api-keys/bocha", headers=headers).json()
    assert body == {"provider": "bocha", "deleted": False}


def test_verify_without_saved_key_returns_404(client, db_session):
    headers, _ = _member_headers(db_session)
    assert client.post("/api/v1/me/api-keys/bocha/verify", headers=headers).status_code == 404
