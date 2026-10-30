import os

# 测试强制离线：必须在 import 任何 app.* 模块之前清空外部服务凭据，
# 否则 app.db.session 的模块级 get_settings() 会先缓存 .env 里的真实 key。
for _service_key in ("DEEPSEEK_API_KEY", "AMAP_WEB_SERVICE_API_KEY", "MEITUAN_HT_TOKEN", "MEITUAN_TRAVEL_TOKEN"):
    os.environ[_service_key] = ""

# 测试环境保持真实权限校验，不绕过会员检查。
os.environ["DEV_BYPASS_AUTH"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.main import create_app
from app.db.session import get_db
from app.models import Base


@pytest.fixture()
def database_engine(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(database_engine) -> Session:
    session = sessionmaker(bind=database_engine, autoflush=False, autocommit=False, expire_on_commit=False)()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def app(database_engine, tmp_path):
    from app.api.album import get_album_storage_root

    test_session_factory = sessionmaker(bind=database_engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override_get_db():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    # 相册存储固定到每个测试自己的 tmp_path，避免读到仓库里的真实 manifest。
    application.dependency_overrides[get_album_storage_root] = lambda: tmp_path
    yield application
    application.dependency_overrides.clear()


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def migrator(monkeypatch, tmp_path):
    """用 Alembic 在隔离 SQLite 文件上建库，供迁移/就绪检查测试共用。"""

    def run(database_path, revision: str) -> None:
        from pathlib import Path

        from alembic import command
        from alembic.config import Config

        from app.core.config import get_settings

        project_root = Path(__file__).resolve().parents[1]
        url = f"sqlite+pysqlite:///{database_path}"
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        config = Config(str(project_root / "alembic.ini"))
        config.set_main_option("script_location", str(project_root / "alembic"))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, revision)

    yield run
    monkeypatch.undo()
    from app.core.config import get_settings as _get_settings

    _get_settings.cache_clear()
