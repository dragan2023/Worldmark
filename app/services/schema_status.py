"""迁移就绪检查：数据库当前版本 vs Alembic head。

只读：不自动 stamp、不自动升级。用于 /health/ready 判断部署是否已完成迁移。
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def alembic_head_revision() -> str | None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def current_database_revision(db: Session) -> str | None:
    try:
        return db.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:  # 表不存在 = 从未迁移
        db.rollback()
        return None
