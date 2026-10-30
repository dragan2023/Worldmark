"""性能量测：合成数据规模下的公开目录/详情/地图 API 响应与查询次数。

- 数据全部为合成数据，写入独立 SQLite 文件，不接触正式库。
- 记录：机器环境、Python/Pillow 版本、数据量、样本数、p50/p95、SQL 条数、响应体大小。
- 用法：
    .venv\\Scripts\\python.exe scripts\\measure_performance.py --rows 100 1000
    .venv\\Scripts\\python.exe scripts\\measure_performance.py --rows 1000 --out .tmp-perf/report.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 量测前阻断外部凭据，避免任何真实服务调用
for _key in ("DEEPSEEK_API_KEY", "AMAP_WEB_SERVICE_API_KEY", "MEITUAN_HT_TOKEN", "MEITUAN_TRAVEL_TOKEN"):
    os.environ[_key] = ""
os.environ.setdefault("APP__ENV", os.environ.get("APP_ENV", "development"))

from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.models import Base  # noqa: E402
from app.models.enums import IPType, PublicationStatus, VerificationStatus  # noqa: E402
from app.models.ip_work import IPWork  # noqa: E402
from app.models.landmark import Landmark  # noqa: E402
from app.models.location import Location  # noqa: E402
from app.models.source import LandmarkSource, Source  # noqa: E402
from app.services.landmark_catalog import CatalogFilters, LandmarkCatalogService  # noqa: E402
from app.services.map_data import MapDataService  # noqa: E402

SAMPLE_COUNT = 30


def _build_dataset(session: Session, rows: int) -> None:
    """写入 rows 条已发布地标，平均分到 3 个门类、rows/10 个作品中。"""
    works: list[IPWork] = []
    work_total = max(1, rows // 10)
    types = [IPType.LITERATURE, IPType.GAME, IPType.SCREEN]
    for index in range(work_total):
        work = IPWork(
            title=f"性能作品{index:04d}",
            aliases=f"perf-alias-{index}",
            ip_type=types[index % 3],
            status=PublicationStatus.PUBLISHED,
        )
        session.add(work)
        works.append(work)
    session.flush()

    now = datetime.now(UTC)
    for index in range(rows):
        work = works[index % len(works)]
        location = Location(
            country_code="CN",
            country_name="中国",
            province_name=f"省{index % 12:02d}",
            city_name=f"市{index % 60:02d}",
            district_name=f"区{index % 200:03d}",
            normalized_address=f"省{index % 12:02d}市{index % 60:02d}区测试路{index}号",
            latitude=30.0 + (index % 500) / 100,
            longitude=110.0 + (index % 500) / 100,
        )
        landmark = Landmark(
            ip_work=work,
            location=location,
            name=f"性能地标{index:05d}",
            description="合成简介，仅用于性能量测。" * 4,
            transit_text="地铁 1 号线到站后步行 500 米。",
            verification_status=VerificationStatus.VERIFIED,
            published_at=now,
        )
        session.add(landmark)
        session.flush()
        source = Source(
            url=f"https://perf.example/{index}",
            title="性能样本来源",
            publisher="load-test",
            source_type="official",
            accessed_at=now,
        )
        session.add(source)
        session.flush()
        session.add(LandmarkSource(landmark_id=landmark.id, source_id=source.id, claim_scope="verification"))
    session.commit()


def _measure(session_factory, counter: dict, operation) -> dict:
    samples: list[float] = []
    queries: list[int] = []
    payload_sizes: list[int] = []
    for _ in range(SAMPLE_COUNT):
        session = session_factory()
        counter["count"] = 0
        started = time.perf_counter()
        try:
            payload = operation(session)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            session.close()
        samples.append(elapsed_ms)
        queries.append(counter["count"])
        payload_sizes.append(len(json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")))

    samples.sort()
    return {
        "samples": SAMPLE_COUNT,
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(samples[min(len(samples) - 1, int(len(samples) * 0.95))], 2),
        "max_ms": round(samples[-1], 2),
        "sql_statements_per_request": round(statistics.mean(queries), 2),
        "max_sql_statements": max(queries),
        "avg_response_bytes": int(statistics.mean(payload_sizes)),
    }


def _measure_http(client, counter: dict, path: str) -> dict:
    samples: list[float] = []
    queries: list[int] = []
    sizes: list[int] = []
    for _ in range(SAMPLE_COUNT):
        counter["count"] = 0
        started = time.perf_counter()
        response = client.get(path)
        elapsed_ms = (time.perf_counter() - started) * 1000
        assert response.status_code == 200, (path, response.status_code)
        samples.append(elapsed_ms)
        queries.append(counter["count"])
        sizes.append(len(response.content))
    samples.sort()
    return {
        "samples": SAMPLE_COUNT,
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(samples[min(len(samples) - 1, int(len(samples) * 0.95))], 2),
        "max_ms": round(samples[-1], 2),
        "sql_statements_per_request": round(statistics.mean(queries), 2),
        "max_sql_statements": max(queries),
        "avg_response_bytes": int(statistics.mean(sizes)),
    }


def run(rows: int) -> dict:
    directory = Path(tempfile.mkdtemp(prefix="worldmark-perf-"))
    database_path = directory / f"perf-{rows}.db"
    engine = create_engine(f"sqlite+pysqlite:///{database_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    counter = {"count": 0}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        counter["count"] += 1

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    setup_started = time.perf_counter()
    with factory() as session:
        _build_dataset(session, rows)
    dataset_seconds = round(time.perf_counter() - setup_started, 2)

    def catalog_page(session):
        result = LandmarkCatalogService(session).list(CatalogFilters(), page=1, page_size=20)
        return {"total": result.total, "items": [item.__dict__ for item in result.items]}

    def catalog_search(session):
        result = LandmarkCatalogService(session).search("性能地标", page=1, page_size=20)
        return {"total": result.total, "items": [item.__dict__ for item in result.items]}

    def detail(session):
        entry = LandmarkCatalogService(session).get_detail(1)
        return {"name": entry.name, "description": entry.description, "sources": list(entry.sources)}

    def filter_options(session):
        options = LandmarkCatalogService(session).filter_options(IPType.GAME)
        return {"countries": [option.value for option in options.countries], "cities": [option.name for option in options.cities]}

    def map_markers(session):
        marker_set = MapDataService(session).list_marker_set(CatalogFilters())
        return {"count": len(marker_set.markers), "truncated": marker_set.truncated,
                "items": [marker.__dict__ for marker in marker_set.markers]}

    results = {
        "dataset_rows": rows,
        "dataset_build_seconds": dataset_seconds,
        "database_bytes": database_path.stat().st_size,
        "service_layer": {
            "catalog_list_page1": _measure(factory, counter, catalog_page),
            "catalog_search": _measure(factory, counter, catalog_search),
            "landmark_detail": _measure(factory, counter, detail),
            "filter_options": _measure(factory, counter, filter_options),
            "map_markers": _measure(factory, counter, map_markers),
        },
        "http_layer": _measure_http_endpoints(factory, counter),
    }
    engine.dispose()
    return results


def _measure_http_endpoints(factory, counter: dict) -> dict:
    """真实请求路径（含 FastAPI 序列化与 Jinja 渲染），热态连续 30 次。"""
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import create_app

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    with TestClient(application) as client:
        client.get("/literature")  # 预热：加载模板与路由
        return {
            "GET /api/v1/landmarks": _measure_http(client, counter, "/api/v1/landmarks?page_size=20"),
            "GET /api/v1/landmarks/1": _measure_http(client, counter, "/api/v1/landmarks/1"),
            "GET /api/v1/maps/landmarks": _measure_http(client, counter, "/api/v1/maps/landmarks"),
            "GET /literature (HTML)": _measure_http(client, counter, "/literature"),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="合成数据下的接口性能量测（隔离数据库）")
    parser.add_argument("--rows", nargs="+", type=int, default=[100, 1000], help="数据规模，可多个")
    parser.add_argument("--out", default=None, help="把报告写入 JSON 文件")
    arguments = parser.parse_args()

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "database": "SQLite (file)",
            "samples_per_operation": SAMPLE_COUNT,
        },
        "results": [run(rows) for rows in arguments.rows],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.out:
        Path(arguments.out).parent.mkdir(parents=True, exist_ok=True)
        Path(arguments.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
