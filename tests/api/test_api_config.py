"""API 配置页接口测试（M4 起仅管理员可用，用依赖注入模拟管理员登录）。"""

import pytest

from app.core.auth import CurrentMember, get_current_member
from app.models.enums import MembershipTier, UserRole
from tests.factories import create_admin


@pytest.fixture(autouse=True)
def admin_login(app, db_session):
    member = create_admin(db_session)
    db_session.commit()
    app.dependency_overrides[get_current_member] = lambda: CurrentMember(
        user_id=member.id, tier=MembershipTier.FREE, role=UserRole.ADMIN
    )
    yield member
    app.dependency_overrides.pop(get_current_member, None)

from app.core.config import get_settings


def _client_by_id(data, client_id):
    return {item["id"]: item for item in data["clients"]}[client_id]


def test_snapshot_masks_secret_and_reports_status(client, monkeypatch):
    monkeypatch.setenv("AMAP_WEB_SERVICE_API_KEY", "abcd1234efgh5678")
    get_settings.cache_clear()
    try:
        response = client.get("/api/v1/api-config")

        assert response.status_code == 200
        data = response.json()
        assert data["can_edit"] is True

        amap = _client_by_id(data, "amap")
        assert amap["status"] == "configured"
        assert amap["apply_url"] == "https://console.amap.com/dev/key/app"
        field = amap["fields"][0]
        assert field["configured"] is True
        assert field["masked"] == "abcd****5678"
        assert "abcd1234efgh5678" not in response.text

        llm = _client_by_id(data, "llm")
        assert llm["status"] == "missing"
        assert [item["env"] for item in llm["fields"]] == [
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_BASE_URL",
            "DEEPSEEK_MODEL",
        ]
        assert {item["id"] for item in data["clients"]} == {"llm", "amap", "meituan", "bocha", "maptile"}
    finally:
        get_settings.cache_clear()


def test_update_writes_env_file_and_refreshes_snapshot(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # conftest 预置的空环境变量优先级高于 .env，这里移除以让 .env 值生效
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        response = client.put("/api/v1/api-config", json={"values": {"DEEPSEEK_API_KEY": "  sk-test-abcdef  "}})

        assert response.status_code == 200
        content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "DEEPSEEK_API_KEY=sk-test-abcdef" in content

        config = response.json()["config"]
        llm = _client_by_id(config, "llm")
        field = next(item for item in llm["fields"] if item["env"] == "DEEPSEEK_API_KEY")
        assert field["configured"] is True
        assert field["masked"].startswith("sk-t")
        assert "sk-test-abcdef" not in response.text
    finally:
        get_settings.cache_clear()


def test_update_preserves_existing_lines_and_appends_new_keys(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "APP_ENV=development\n# 手工注释\nMEITUAN_HT_TOKEN=old-token\n",
        encoding="utf-8",
    )
    response = client.put(
        "/api/v1/api-config",
        json={
            "values": {
                "MEITUAN_HT_TOKEN": "new-token",
                "MAP_TILE_URL": "https://tile.example/{z}/{x}/{y}.png",
            }
        },
    )

    assert response.status_code == 200
    lines = (tmp_path / ".env").read_text(encoding="utf-8").splitlines()
    assert "APP_ENV=development" in lines
    assert "# 手工注释" in lines
    assert "MEITUAN_HT_TOKEN=new-token" in lines
    assert "old-token" not in lines
    assert lines.index("APP_ENV=development") < lines.index("MEITUAN_HT_TOKEN=new-token")
    assert lines[-1] == "MAP_TILE_URL=https://tile.example/{z}/{x}/{y}.png"


def test_update_rejects_unknown_env_names(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = client.put("/api/v1/api-config", json={"values": {"HACKED_ENV": "x"}})
    assert response.status_code == 400
    assert "HACKED_ENV" in response.json()["detail"]


def test_update_rejects_values_with_newlines(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = client.put("/api/v1/api-config", json={"values": {"BOCHA_API_KEY": "line1\nline2"}})
    assert response.status_code == 422


def test_update_refuses_cross_origin_request(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = client.put(
        "/api/v1/api-config",
        json={"values": {"BOCHA_API_KEY": "x"}},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_update_refuses_production_env(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        response = client.put("/api/v1/api-config", json={"values": {"BOCHA_API_KEY": "x"}})
        assert response.status_code == 403
    finally:
        get_settings.cache_clear()


def test_verify_reports_missing_configuration(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AMAP_WEB_SERVICE_API_KEY", "")
    get_settings.cache_clear()
    try:
        response = client.post("/api/v1/api-config/verify", json={"client_id": "amap"})
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert "未配置" in body["message"]
    finally:
        get_settings.cache_clear()


def test_verify_maptile_checks_placeholder(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAP_TILE_URL", "https://tile.example/{z}/{x}/{y}.png")
    get_settings.cache_clear()
    try:
        response = client.post("/api/v1/api-config/verify", json={"client_id": "maptile"})
        assert response.status_code == 200
        assert response.json()["ok"] is True
    finally:
        get_settings.cache_clear()


def test_verify_unknown_client_returns_404(client):
    response = client.post("/api/v1/api-config/verify", json={"client_id": "nope"})
    assert response.status_code == 404


def test_api_config_page_renders(client):
    response = client.get("/settings/api")
    assert response.status_code == 200
    assert "API 配置" in response.text
