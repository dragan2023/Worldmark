from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.landmark_catalog import CatalogNotFound, LandmarkCatalogService
from app.web.catalog import _with_thumbnails

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))

IP_TYPE_LABELS = {"literature": "文学", "game": "游戏", "screen": "影视"}
IP_TYPE_MODULES = {"literature": "literature", "game": "games", "screen": "screen"}


@router.get("/works/{work_id}", response_class=HTMLResponse, include_in_schema=False)
def work_detail(work_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    try:
        work = LandmarkCatalogService(db).get_work(work_id)
    except CatalogNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "works/detail.html",
        {
            "request": request,
            "title": f"{work.title}｜IP 地标旅游",
            "work": work,
            "items": _with_thumbnails(work.landmarks),
            "ip_type_label": IP_TYPE_LABELS.get(work.ip_type.value, work.ip_type.value),
            "catalog_url": f"/{IP_TYPE_MODULES.get(work.ip_type.value, 'literature')}",
        },
    )
