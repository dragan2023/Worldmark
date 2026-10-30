"""Alembic 迁移的方言兼容辅助。

Alembic 默认按 VARCHAR(32) 创建 alembic_version，而本项目 0007 修订号
`0007_itinerary_day_travel_context` 有 33 个字符：SQLite 不校验长度，
PostgreSQL 会在写入版本号时抛 value too long。
"""

from __future__ import annotations

VERSION_TABLE_DDL = (
    "CREATE TABLE alembic_version ("
    "version_num VARCHAR(64) NOT NULL, "
    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
)


def ensure_version_table_width(connection) -> None:
    """空库首次迁移前建成 VARCHAR(64)；已有库仅在列宽不足时加宽。"""
    if connection.dialect.name != "postgresql":
        return
    exists = connection.exec_driver_sql("SELECT to_regclass('public.alembic_version')").scalar()
    if not exists:
        connection.exec_driver_sql(VERSION_TABLE_DDL)
        connection.commit()
        return
    width = connection.exec_driver_sql(
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_name = 'alembic_version' AND column_name = 'version_num'"
    ).scalar()
    if width is not None and width < 64:
        connection.exec_driver_sql("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
        connection.commit()
