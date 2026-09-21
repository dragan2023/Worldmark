"""一次性迁移：users 表增加 role / status / last_login_at 字段并回填。

幂等：重复执行安全。用法：.venv/Scripts/python.exe scripts/migrate_user_roles.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.enums import UserRole, UserStatus  # noqa: E402

NEW_COLUMNS: dict[str, str] = {
    "role": f"VARCHAR(16) NOT NULL DEFAULT '{UserRole.LEVEL2.value}'",
    "status": f"VARCHAR(16) NOT NULL DEFAULT '{UserStatus.ACTIVE.value}'",
    "last_login_at": "DATETIME NULL",
}

LANDMARK_NEW_COLUMNS: dict[str, str] = {
    "deleted_at": "DATETIME NULL",
}

# 用户名回填规则：存量用户取邮箱 @ 前缀，冲突时追加序号
USERNAME_BACKFILL_SQL = "UPDATE users SET username = lower(substr(email, 1, instr(email || '@', '@') - 1)) WHERE username IS NULL"


def main() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        existing = {column["name"] for column in inspector.get_columns("users")}
        for column_name, ddl in NEW_COLUMNS.items():
            if column_name not in existing:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {ddl}"))
                print(f"users.{column_name}: added")
            else:
                print(f"users.{column_name}: exists")

        landmark_existing = {column["name"] for column in inspector.get_columns("landmarks")}
        for column_name, ddl in LANDMARK_NEW_COLUMNS.items():
            if column_name not in landmark_existing:
                connection.execute(text(f"ALTER TABLE landmarks ADD COLUMN {column_name} {ddl}"))
                print(f"landmarks.{column_name}: added")
            else:
                print(f"landmarks.{column_name}: exists")

        # 用户名字段：登录标识（英文账户名）
        if "username" not in existing:
            connection.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(32) NULL"))
            print("users.username: added")
        else:
            print("users.username: exists")
        connection.execute(text(USERNAME_BACKFILL_SQL))
        # 回填冲突处理：同名追加 -2、-3 …（SQLite 无窗口函数时代做法）
        connection.execute(text(
            "UPDATE users SET username = username || '-2' WHERE id IN ("
            "SELECT id FROM users WHERE username IN (SELECT username FROM users GROUP BY username HAVING COUNT(*) > 1) "
            "AND id NOT IN (SELECT MIN(id) FROM users GROUP BY username))"
        ))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users (username)"))
        print("users.username: backfill + unique index done")

        connection.execute(
            text(f"UPDATE users SET role = '{UserRole.ADMIN.value}' WHERE is_admin = 1")
        )
        connection.execute(
            text("UPDATE users SET role = 'admin' WHERE email = 'dev@iplandmarks.local'")
        )
        connection.execute(
            text(f"UPDATE users SET role = '{UserRole.LEVEL2.value}' WHERE role IS NULL OR role = ''")
        )
        connection.execute(
            text(f"UPDATE users SET status = '{UserStatus.ACTIVE.value}' WHERE status IS NULL OR status = ''")
        )
        print("backfill done")

    Base.metadata.create_all(engine)
    print("schema create_all ok")


if __name__ == "__main__":
    main()
