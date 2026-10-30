"""迁移验收：空库、0007 旧库、手工半升级库都能升级到与模型一致的结构。

这些测试故意不用 ``Base.metadata.create_all``：被测对象就是 Alembic 迁移本身。
历史数据全部为合成快照，不读取任何正式库或用户资料。
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import create_app
from app.models.user import User
from app.models.user_api_key import UserApiKey

PROJECT_ROOT = Path(__file__).resolve().parents[2]
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,32}$")


def _legacy_rows() -> list[tuple[int, str, int]]:
    """Synthetic 0007-era accounts: duplicate prefixes, blanks and odd names."""
    return [
        (1, "alice@example.org", 0),
        (2, "alice@another.org", 0),
        (3, "bob@a.org", 0),
        (4, "bob@b.org", 0),
        (5, "bob@c.org", 0),
        (6, "@nolocal.org", 0),
        (7, f"{'verylongprefix' * 4}@example.org", 0),
        (8, "张三@example.cn", 0),
        (9, "root@example.org", 1),
        (10, "a.b-c@example.org", 0),
        (11, "", 0),
        (12, "ALICE@upper.org", 0),
    ]


def _seed_legacy_users(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        for user_id, email, is_admin in _legacy_rows():
            connection.execute(
                "INSERT INTO users (id, email, password_hash, is_admin) VALUES (?, ?, ?, ?)",
                (user_id, email, "legacy-hash", is_admin),
            )
        connection.execute(
            "INSERT INTO locations (id, country_code, country_name, normalized_address)"
            " VALUES (1, 'CN', '中国', '山西省朔州市应县木塔')"
        )
        connection.execute(
            "INSERT INTO ip_works (id, title, ip_type, status) VALUES (1, '黑神话：悟空', 'game', 'published')"
        )
        connection.execute(
            "INSERT INTO landmarks (id, ip_work_id, location_id, name, description, verification_status, published_at)"
            " VALUES (1, 1, 1, '应县木塔', '合成简介', 'verified', CURRENT_TIMESTAMP)"
        )
        connection.commit()


def _assert_model_schema(database_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        user_columns = {column["name"]: column for column in inspector.get_columns("users")}
        assert {"username", "role", "status", "last_login_at"} <= set(user_columns)
        assert user_columns["username"]["nullable"] is False
        assert {"deleted_at"} <= {column["name"] for column in inspector.get_columns("landmarks")}
        assert "user_api_keys" in inspector.get_table_names()
        unique_names = {
            constraint["name"] for constraint in inspector.get_unique_constraints("users")
        } | {
            index["name"] for index in inspector.get_indexes("users") if index.get("unique")
        }
        assert any(name and "username" in name for name in unique_names)
    finally:
        engine.dispose()


def test_empty_database_upgrades_and_supports_accounts(migrator, monkeypatch, tmp_path):
    database_path = tmp_path / "fresh.db"
    migrator(database_path, "head")
    _assert_model_schema(database_path)

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
        registered = client.post(
            "/api/v1/auth/register",
            json={"username": "migrator", "email": "migrator@example.org", "password": "correct-horse"},
        )
        assert registered.status_code == 201, registered.text
        token = registered.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        logged_in = client.post(
            "/api/v1/auth/login",
            json={"username": "migrator", "password": "correct-horse"},
        )
        assert logged_in.status_code == 200, logged_in.text
        assert client.get("/api/v1/auth/me", headers=headers).json()["role"] == "level2"

        saved = client.put("/api/v1/me/api-keys/deepseek", json={"value": "sk-test-0000", "verify": False}, headers=headers)
        assert saved.status_code == 200, saved.text
        listed = client.get("/api/v1/me/api-keys", headers=headers).json()["items"]
        assert next(item for item in listed if item["provider"] == "deepseek")["configured"] is True

    with factory() as session:
        user = session.scalar(select(User).where(User.username == "migrator"))
        assert user is not None and user.role == "level2" and user.status == "active"
        assert session.scalar(select(UserApiKey).where(UserApiKey.user_id == user.id)) is not None
    engine.dispose()


def test_legacy_0007_database_backfills_unique_usernames(migrator, tmp_path):
    database_path = tmp_path / "legacy.db"
    migrator(database_path, "0007_itinerary_day_travel_context")
    _seed_legacy_users(database_path)
    migrator(database_path, "head")
    _assert_model_schema(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute("SELECT id, email, username, role, status, is_admin FROM users ORDER BY id").fetchall()
        landmark_deleted = connection.execute("SELECT deleted_at FROM landmarks WHERE id = 1").fetchone()[0]

    usernames = [row[2] for row in rows]
    assert len(usernames) == len(set(usernames)), usernames
    assert all(USERNAME_PATTERN.match(name or "") for name in usernames), usernames
    assert rows[0][2] != rows[1][2]  # duplicate mail prefix resolved deterministically
    assert len({rows[2][2], rows[3][2], rows[4][2]}) == 3  # three同名前缀不共用 -2
    by_id = {row[0]: row for row in rows}
    assert by_id[9][3] == "admin" and by_id[9][5] == 1  # 既有管理员保留
    assert by_id[1][3] == "level2"  # 不自动创建新管理员
    assert all(row[4] == "active" for row in rows)
    assert landmark_deleted is None


def test_partially_patched_database_upgrades_without_duplicate_indexes(migrator, tmp_path):
    """模拟曾运行旧 migrate_user_roles.py 的库：列已加、索引名不同。"""
    database_path = tmp_path / "patched.db"
    migrator(database_path, "0007_itinerary_day_travel_context")
    _seed_legacy_users(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'level2'")
        connection.execute("ALTER TABLE users ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active'")
        connection.execute("ALTER TABLE users ADD COLUMN last_login_at DATETIME NULL")
        connection.execute("ALTER TABLE users ADD COLUMN username VARCHAR(32) NULL")
        connection.execute(
            "UPDATE users SET username = lower(substr(email, 1, instr(email || '@', '@') - 1)) WHERE username IS NULL"
        )
        connection.execute("ALTER TABLE landmarks ADD COLUMN deleted_at DATETIME NULL")
        connection.commit()

    migrator(database_path, "head")
    _assert_model_schema(database_path)

    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    unique_username_indexes = [
        index["name"]
        for index in inspect(engine).get_indexes("users")
        if index.get("unique") and index.get("column_names") == ["username"]
    ]
    engine.dispose()
    assert len(unique_username_indexes) == 1

    with sqlite3.connect(database_path) as connection:
        usernames = [row[0] for row in connection.execute("SELECT username FROM users")]
    assert all(name for name in usernames)
    assert len(usernames) == len(set(usernames))
