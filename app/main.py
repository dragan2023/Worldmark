from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.admin import router as admin_router
from app.api.agent import router as agent_router
from app.api.auth import router as auth_router
from app.api.user_keys import router as user_keys_router
from app.api.contributor import router as contributor_router
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
from app.web.api_config import router as api_config_web_router
from app.web.catalog import router as catalog_router
from app.web.home import router as home_router
from app.web.maps import router as maps_web_router
from app.web.itineraries import router as itineraries_web_router
from app.web.routes import router as routes_web_router
from app.web.search import router as search_web_router
from app.web.works import router as works_web_router
from app.services.landmark_albums import ALBUM_ROOT

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def create_app() -> FastAPI:
    app = FastAPI(title="IP 地标旅游应用", version="0.1.0")
    static_directory = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_directory)), name="static")
    album_directory = Path(__file__).resolve().parents[1] / ALBUM_ROOT / "images"
    app.mount("/contributions/landmark-albums/images", StaticFiles(directory=str(album_directory)), name="landmark-album-images")
    staging_directory = Path(__file__).resolve().parents[1] / "uploads" / "landmark_albums"
    staging_directory.mkdir(parents=True, exist_ok=True)
    app.mount("/staging/landmark-albums", StaticFiles(directory=str(staging_directory)), name="landmark-album-staging")
    app.include_router(home_router)
    app.include_router(search_web_router)
    app.include_router(works_web_router)
    app.include_router(catalog_router)
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
    app.include_router(admin_users_router)
    app.include_router(admin_router)

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=getattr(exc, "headers", None))
        if exc.status_code == 404:
            title, message = "页面不存在", "你访问的页面不存在或已被移除。"
        elif exc.status_code == 403:
            title, message = "无权访问", "当前账号无权访问该内容。"
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
