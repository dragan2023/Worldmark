"""只读结构差异报告：数据库实际结构 vs ORM 模型。

用于排查「迁移已跑但模型不匹配」的旧库，不建表、不改数据、不执行 create_all。

用法：
    .venv\\Scripts\\python.exe scripts\\check_schema_drift.py            # 读 DATABASE_URL
    .venv\\Scripts\\python.exe scripts\\check_schema_drift.py --url sqlite+pysqlite:///./x.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402


def collect_drift(database_url: str) -> dict[str, object]:
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        missing_tables: list[str] = []
        missing_columns: dict[str, list[str]] = {}
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                missing_tables.append(table.name)
                continue
            actual = {column["name"] for column in inspector.get_columns(table.name)}
            absent = [column.name for column in table.columns if column.name not in actual]
            if absent:
                missing_columns[table.name] = absent
        return {"missing_tables": missing_tables, "missing_columns": missing_columns}
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="报告数据库结构与 ORM 模型的差异（只读）")
    parser.add_argument("--url", default=None, help="数据库 URL，默认读取 Settings.database_url")
    arguments = parser.parse_args()
    database_url = arguments.url or get_settings().database_url
    drift = collect_drift(database_url)
    missing_tables = drift["missing_tables"]
    missing_columns = drift["missing_columns"]
    if not missing_tables and not missing_columns:
        print("结构与模型一致。")
        return 0
    if missing_tables:
        print("缺少数据表：" + "、".join(missing_tables))
    for table, columns in missing_columns.items():
        print(f"{table} 缺少列：" + "、".join(columns))
    print("建议执行：.venv\\Scripts\\python.exe -m alembic upgrade head")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
