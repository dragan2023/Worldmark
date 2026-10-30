from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.landmark_catalog import LandmarkCatalogService
from app.web.catalog import _with_thumbnails

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))

PAGE_SIZE = 20


@router.get("/search", response_class=HTMLResponse, include_in_schema=False)
def search(
    request: Request,
    q: str = Query(default="", max_length=255),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    query = q.strip()
    items = ()
    total = 0
    total_pages = 1
    current_page = 1
    if query:
        result = LandmarkCatalogService(db).search(query, page=page, page_size=PAGE_SIZE)
        current_page = min(max(result.page, 1), result.total_pages)
        if current_page != result.page:  # 超页时回到最后一页有效结果
            result = LandmarkCatalogService(db).search(query, page=current_page, page_size=PAGE_SIZE)
        items = _with_thumbnails(result.items)
        total = result.total
        total_pages = result.total_pages

    def page_url(target_page: int) -> str:
        return urlencode({"q": query, "page": target_page})

    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "request": request,
            "title": f"搜索「{query}」｜IP 地标旅游",
            "query": query,
            "items": items,
            "total": total,
            "page": current_page,
            "total_pages": total_pages,
            "page_url": page_url,
        },
    )
