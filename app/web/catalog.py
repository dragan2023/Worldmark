from pathlib import Path
from urllib.parse import urlencode

from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import IPType
from app.services.landmark_catalog import CatalogFilters, CatalogNotFound, LandmarkCatalogService
from app.services.landmark_albums import LandmarkAlbumService

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODULES = {
    "literature": (IPType.LITERATURE, "文学地标", "书名"),
    "games": (IPType.GAME, "游戏地标", "游戏名"),
    "screen": (IPType.SCREEN, "影视地标", "影视剧名"),
}


def _with_thumbnails(items) -> tuple:
    album_service = LandmarkAlbumService(PROJECT_ROOT)
    return tuple(replace(entry, thumbnail_url=album_service.first_photo_url(entry.ip_type, entry.name)) for entry in items)


def _catalog_context(request: Request, module: str, db: Session) -> dict[str, object]:
    ip_type, module_name, work_label = MODULES[module]
    params = request.query_params
    filters = CatalogFilters.from_values(
        ip_type=ip_type,
        work=params.get("work"),
        country=params.get("country"),
        province=params.get("province"),
        city=params.get("city"),
        landmark=params.get("landmark"),
    )
    page = max(int(params.get("page", "1")), 1) if params.get("page", "1").isdigit() else 1
    service = LandmarkCatalogService(db)
    result = service.list(filters, page=page, page_size=20)
    export_params = {"ip_type": ip_type.value}
    export_params.update({key: value for key, value in params.items() if key in {"work", "landmark", "country", "province", "city"} and value})

    def page_url(target_page: int) -> str:
        query = {key: value for key, value in params.items() if key != "page" and value}
        query["page"] = str(target_page)
        return urlencode(query)

    return {
        "request": request,
        "title": f"{module_name}｜IP 地标旅游",
        "module": module,
        "module_name": module_name,
        "work_label": work_label,
        "filters": filters,
        "items": _with_thumbnails(result.items),
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "total_pages": result.total_pages,
        "filter_options": service.filter_options(ip_type),
        "page_url": page_url,
        "export_query": urlencode(export_params),
        "map_query": urlencode({key: value for key, value in export_params.items() if key != "ip_type"}),
    }


def _catalog_page(module: str, request: Request, db: Session) -> HTMLResponse:
    return templates.TemplateResponse(request, "catalog/index.html", _catalog_context(request, module, db))


@router.get("/literature", response_class=HTMLResponse, include_in_schema=False)
def literature_catalog(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return _catalog_page("literature", request, db)


@router.get("/games", response_class=HTMLResponse, include_in_schema=False)
def game_catalog(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return _catalog_page("games", request, db)


@router.get("/screen", response_class=HTMLResponse, include_in_schema=False)
def screen_catalog(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return _catalog_page("screen", request, db)


@router.get("/landmarks/{landmark_id}", response_class=HTMLResponse, include_in_schema=False)
def landmark_detail(landmark_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    try:
        entry = LandmarkCatalogService(db).get_detail(landmark_id)
    except CatalogNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "catalog/detail.html",
        {
            "request": request,
            "title": f"{entry.name}｜IP 地标旅游",
            "item": entry,
            "album_photos": LandmarkAlbumService(PROJECT_ROOT).get_photos(entry.ip_type, entry.name),
        },
    )
