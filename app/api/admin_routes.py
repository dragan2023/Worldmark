from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.admin import require_admin
from app.db.session import get_db
from app.schemas.maps import RouteDetailResponse, RouteStopResponse
from app.services.route_builder import RouteBuilderService, RouteStopDraft, RouteUnavailable, RouteValidationError

router = APIRouter(prefix="/api/v1/admin/routes", tags=["admin-routes"])


class RouteStopRequest(BaseModel):
    landmark_id: int = Field(gt=0)
    stay_minutes: int | None = Field(default=None, ge=1, le=1440)
    note: str | None = Field(default=None, max_length=2000)


class RouteCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=4000)
    duration_text: str | None = Field(default=None, max_length=100)
    stops: list[RouteStopRequest] = Field(min_length=2, max_length=30)


@router.post("", dependencies=[Depends(require_admin)])
def create_route(payload: RouteCreateRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        route = RouteBuilderService(db).create(
            payload.title,
            payload.summary,
            payload.duration_text,
            [RouteStopDraft(item.landmark_id, item.stay_minutes, item.note) for item in payload.stops],
        )
    except RouteValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": route.id, "status": route.status}


@router.get("/{route_id}/preview", response_model=RouteDetailResponse, dependencies=[Depends(require_admin)])
def preview_route(route_id: int, db: Session = Depends(get_db)) -> RouteDetailResponse:
    try:
        route = RouteBuilderService(db).preview(route_id)
    except RouteUnavailable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RouteDetailResponse(
        id=route.id,
        title=route.title,
        summary=route.summary,
        duration_text=route.duration_text,
        stops=[RouteStopResponse(**stop.__dict__) for stop in route.stops],
        disclaimer="预览只表达建议访问顺序，不代表实时道路距离、交通时间或导航指引。",
    )


@router.post("/{route_id}/publish", dependencies=[Depends(require_admin)])
def publish_route(route_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        route = RouteBuilderService(db).publish(route_id)
    except (RouteValidationError, RouteUnavailable) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": route.id, "status": route.status}
