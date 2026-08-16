from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_entitlement
from app.db.session import get_db
from app.schemas.maps import RouteDetailResponse, RouteStopResponse
from app.services.route_builder import RouteBuilderService, RouteUnavailable

router = APIRouter(prefix="/api/v1/routes", tags=["routes"])


@router.get("/{route_id}", response_model=RouteDetailResponse, dependencies=[Depends(require_entitlement("static_route"))])
def get_route(route_id: int, db: Session = Depends(get_db)) -> RouteDetailResponse:
    try:
        route = RouteBuilderService(db).get_public(route_id)
    except RouteUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RouteDetailResponse(
        id=route.id,
        title=route.title,
        summary=route.summary,
        duration_text=route.duration_text,
        stops=[RouteStopResponse(**stop.__dict__) for stop in route.stops],
        disclaimer="路线仅表达建议访问顺序，不代表实时道路距离、交通时间或导航指引。",
    )
