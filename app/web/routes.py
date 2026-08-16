from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth import require_entitlement
from app.db.session import get_db
from app.services.route_builder import RouteBuilderService, RouteUnavailable

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/routes/{route_id}", response_class=HTMLResponse, include_in_schema=False)
def route_detail(
    route_id: int,
    request: Request,
    _: object = Depends(require_entitlement("static_route")),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        route = RouteBuilderService(db).get_public(route_id)
    except RouteUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "routes/detail.html",
        {"request": request, "title": f"{route.title}｜IP 地标旅游", "route": route},
    )
