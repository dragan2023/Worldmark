from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.landmark_catalog import CatalogFilters, LandmarkCatalogService
from app.web.catalog import _with_thumbnails

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    featured = _with_thumbnails(LandmarkCatalogService(db).list(CatalogFilters(), page=1, page_size=6).items)
    return templates.TemplateResponse(request, "home.html", {"title": "IP 地标旅游", "featured": featured, "query": ""})
