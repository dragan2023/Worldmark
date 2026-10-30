"""阶段06 回归：查询次数、就绪检查、限速清理、点位上限与可观测性。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import event, select

from app.core import rate_limit
from app.core.auth import create_access_token
from app.models.enums import MembershipTier, UserRole
from tests.factories import create_admin, create_landmark, create_member


def _headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


# ------------------------------------------------------------ 就绪检查


def test_ready_reports_pending_migration_for_create_all_database(client):
    """测试库由 create_all 建表，没有 alembic_version：就绪应为 degraded。"""
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["migration"] == "pending"


def test_ready_is_ok_after_real_migrations(migrator, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.session import get_db
    from app.main import create_app

    database_path = tmp_path / "ready.db"
    migrator(database_path, "head")
    engine = create_engine(f"sqlite+pysqlite:///{database_path}", connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    with TestClient(application) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["checks"]["migration"] == "ok"
        assert "APP_SECRET_KEY" not in response.text  # 不泄露配置
    engine.dispose()


def test_live_stays_process_only(client):
    assert client.get("/health/live").json() == {"status": "ok"}


# ------------------------------------------------------------ 查询次数


def test_admin_user_list_uses_count_and_batch_membership(client, db_session, database_engine):
    admin = create_admin(db_session)
    create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(database_engine, "before_cursor_execute", record)
    try:
        body = client.get("/api/v1/admin/users?q=nomatch", headers=_headers(admin)).json()
    finally:
        event.remove(database_engine, "before_cursor_execute", record)

    assert body["total"] == 0
    assert len(statements) <= 4, statements
    assert any("count(" in statement.lower() for statement in statements)


def test_admin_landmark_list_counts_in_database(client, db_session, database_engine):
    admin = create_admin(db_session)
    create_landmark(db_session, landmark_name="计数地标")

    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(database_engine, "before_cursor_execute", record)
    try:
        body = client.get("/api/v1/admin/landmarks?status=published", headers=_headers(admin)).json()
    finally:
        event.remove(database_engine, "before_cursor_execute", record)

    assert body["total"] == 1
    # COUNT 而不是把全部实体拉回来求 len()
    count_statements = [s for s in statements if "count(" in s.lower()]
    assert count_statements, statements


def test_filter_options_keeps_same_city_name_across_provinces(db_session):
    from app.models.enums import IPType
    from app.services.landmark_catalog import LandmarkCatalogService

    create_landmark(db_session, landmark_name="甲地标", province_name="山西省", city_name="城区")
    create_landmark(
        db_session, work_title="另一部作品", landmark_name="乙地标", province_name="河北省", city_name="城区"
    )

    options = LandmarkCatalogService(db_session).filter_options(IPType.GAME)
    cities = [option for option in options.cities if option.name == "城区"]

    assert len(cities) == 2
    assert {option.province_name for option in cities} == {"山西省", "河北省"}


# ------------------------------------------------------------ 限速清理


def test_rate_limit_prunes_expired_keys(monkeypatch):
    rate_limit.clear_all()
    monkeypatch.setattr(rate_limit, "_PRUNE_THRESHOLD", 4)

    for index in range(4):
        rate_limit.register_failure(f"10.0.0.{index}")
    assert rate_limit.tracked_keys() == 4

    # 把窗口推进到全部过期，再记录一次失败：旧键应被清理
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: 10_000_000.0)
    rate_limit.register_failure("10.0.0.99")

    assert rate_limit.tracked_keys() == 1
    monkeypatch.undo()
    rate_limit.clear_all()


def test_login_rate_limit_returns_retry_after(client, db_session):
    member = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    rate_limit.clear_all()
    try:
        for _ in range(8):
            client.post("/api/v1/auth/login", json={"username": member.username, "password": "wrong"})
        response = client.post("/api/v1/auth/login", json={"username": member.username, "password": "wrong"})
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) >= 1
    finally:
        rate_limit.clear_all()


# ------------------------------------------------------ 地图点位上限


def test_map_markers_are_capped_with_explicit_truncation(client, db_session, monkeypatch):
    from app.services import map_data as module

    monkeypatch.setattr(module, "MAX_MARKERS", 2)
    for index in range(3):
        create_landmark(db_session, landmark_name=f"点位地标{index}", work_title=f"作品{index}")

    body = client.get("/api/v1/maps/landmarks?ip_type=game").json()

    assert len(body["items"]) == 2
    assert body["truncated"] is True
    assert body["limit"] == 2


# ------------------------------------------------------------ 可观测性


def test_response_carries_request_id_header(client):
    response = client.get("/health/live")
    assert response.headers["X-Request-ID"]


def test_meituan_package_version_is_pinned():
    from app.integrations.meituan_travel_mcp import PINNED_PACKAGE, resolve_package

    assert resolve_package() == PINNED_PACKAGE
    assert not PINNED_PACKAGE.endswith("@latest")
    assert "@" in PINNED_PACKAGE.split("/")[-1]


def test_meituan_package_rejects_latest_override(monkeypatch):
    import pytest as pytest_module

    from app.integrations.meituan_travel_mcp import MeituanMcpUnavailable, resolve_package

    monkeypatch.setenv("MEITUAN_SKILL_PACKAGE", "@meituan-travel/ht-ai@latest")
    with pytest_module.raises(MeituanMcpUnavailable, match="固定版本"):
        resolve_package()


def test_catalog_export_service_is_removed_and_documented():
    assert not Path("app/services/export_landmarks.py").exists()
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "已下线" in readme
    assert "LandmarkExportService" in readme
