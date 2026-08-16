import os

# 测试强制离线：必须在 import 任何 app.* 模块之前清空外部服务凭据，
# 否则 app.db.session 的模块级 get_settings() 会先缓存 .env 里的真实 key。
for _service_key in ("DEEPSEEK_API_KEY", "AMAP_WEB_SERVICE_API_KEY", "MEITUAN_HT_TOKEN", "MEITUAN_TRAVEL_TOKEN", "BOCHA_API_KEY"):
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
def app(database_engine):
    test_session_factory = sessionmaker(bind=database_engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override_get_db():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client
