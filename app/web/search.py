from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.landmark_catalog import LandmarkCatalogService
from app.web.catalog import _with_thumbnails

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/search", response_class=HTMLResponse, include_in_schema=False)
def search(
    request: Request,
    q: str = Query(default="", max_length=255),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    query = q.strip()
    items = ()
    total = 0
    if query:
        result = LandmarkCatalogService(db).search(query, page=1, page_size=30)
        items = _with_thumbnails(result.items)
        total = result.total
    return templates.TemplateResponse(
        request,
        "search.html",
        {"request": request, "title": f"搜索「{query}」｜IP 地标旅游", "query": query, "items": items, "total": total},
    )
