from pathlib import Path
import logging
import time
import uuid
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.admin import router as admin_router
from app.api.agent import router as agent_router
from app.api.auth import router as auth_router
from app.api.user_keys import router as user_keys_router
from app.api.contributor import router as contributor_router
from app.api.me_contributions import router as me_contributions_router
from app.api.admin_users import router as admin_users_router
from app.api.api_config import router as api_config_router
from app.api.album import router as album_router
from app.api.itineraries import router as itineraries_router
from app.api.landmarks import router as landmarks_router
from app.api.maps import router as maps_router
from app.api.routes import router as routes_router
from app.api.admin_routes import router as admin_routes_router
from app.api.meta import router as meta_router
from app.web.agent import router as agent_web_router
from app.web.admin import router as admin_web_router
from app.web.auth import router as auth_web_router
from app.web.album import router as album_web_router
from app.web.album_images import router as album_images_router
from app.web.api_config import router as api_config_web_router
from app.web.catalog import router as catalog_router
from app.web.contributions import router as contributions_web_router
from app.web.home import router as home_router
from app.web.maps import router as maps_web_router
from app.web.itineraries import router as itineraries_web_router
from app.web.routes import router as routes_web_router
from app.web.search import router as search_web_router
from app.web.works import router as works_web_router
from app.core.auth import LoginRequired, safe_next_path
from app.db.session import get_db
from app.services.schema_status import alembic_head_revision, current_database_revision

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
logger = logging.getLogger("app.http")


def create_app() -> FastAPI:
    app = FastAPI(title="IP 地标旅游应用", version="0.1.0")
    static_directory = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_directory)), name="static")

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        """最小可观测性：请求标识、路径、状态码、耗时。不记录查询串、请求体或任何密钥。"""
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception("request failed id=%s %s %s %.0fms", request_id, request.method, request.url.path, duration_ms)
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        if not request.url.path.startswith("/static"):
            logger.info(
                "request id=%s method=%s path=%s status=%s duration_ms=%.0f",
                request_id, request.method, request.url.path, response.status_code, duration_ms,
            )
        return response

    app.include_router(album_images_router)
    app.include_router(home_router)
    app.include_router(search_web_router)
    app.include_router(works_web_router)
    app.include_router(catalog_router)
    app.include_router(contributions_web_router)
    app.include_router(maps_web_router)
    app.include_router(itineraries_web_router)
    app.include_router(routes_web_router)
    app.include_router(agent_web_router)
    app.include_router(album_web_router)
    app.include_router(api_config_web_router)
    app.include_router(auth_web_router)
    app.include_router(admin_web_router)
    app.include_router(meta_router)
    app.include_router(landmarks_router)
    app.include_router(maps_router)
    app.include_router(routes_router)
    app.include_router(itineraries_router)
    app.include_router(agent_router)
    app.include_router(album_router)
    app.include_router(api_config_router)
    app.include_router(admin_routes_router)
    app.include_router(auth_router)
    app.include_router(user_keys_router)
    app.include_router(contributor_router)
    app.include_router(me_contributions_router)
    app.include_router(admin_users_router)
    app.include_router(admin_router)

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        """存活检查：仅表示进程可响应，不访问数据库或外部服务。"""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready(response: Response, db: Session = Depends(get_db)) -> dict[str, object]:
        """就绪检查：轻量数据库连接 + 迁移版本核对，不访问收费接口、不返回配置。"""
        checks: dict[str, object] = {}
        try:
            db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except SQLAlchemyError:
            checks["database"] = "unavailable"
        try:
            head = alembic_head_revision()
            current = current_database_revision(db)
            checks["migration"] = "ok" if current == head else "pending"
            checks["schema_revision"] = current
        except (SQLAlchemyError, OSError):
            checks["migration"] = "unknown"
        healthy = checks.get("database") == "ok" and checks.get("migration") == "ok"
        if not healthy:
            response.status_code = 503
        return {"status": "ok" if healthy else "degraded", "checks": checks}

    @app.exception_handler(LoginRequired)
    async def login_required_handler(request: Request, exc: LoginRequired):
        next_path = safe_next_path(exc.next_url)
        target = "/login" + (f"?next={quote(next_path)}" if next_path != "/" else "")
        return RedirectResponse(target, status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=getattr(exc, "headers", None))
        detail = exc.detail if isinstance(exc.detail, str) else None
        if exc.status_code == 404:
            title, message = "页面不存在", "你访问的页面不存在或已被移除。"
        elif exc.status_code == 403:
            title, message = "无权访问", detail or "当前账号无权访问该内容。"
        elif exc.status_code == 401:
            title, message = "请先登录", detail or "登录后再访问该页面。"
        else:
            title, message = "出错了", "服务器暂时无法处理该请求，请稍后重试。"
        return templates.TemplateResponse(
            request,
            "error.html",
            {"request": request, "status_code": exc.status_code, "title": title, "message": message},
            status_code=exc.status_code,
        )

    return app


app = create_app()
