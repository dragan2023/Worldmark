from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.landmarks import _filters
from app.core.auth import require_entitlement
from app.db.session import get_db
from app.models.enums import IPType
from app.schemas.maps import MapMarkerListResponse, MapMarkerResponse
from app.services.map_data import MapDataService

router = APIRouter(prefix="/api/v1/maps", tags=["maps"])


@router.get("/landmarks", response_model=MapMarkerListResponse, dependencies=[Depends(require_entitlement("static_map"))])
def list_map_landmarks(
    ip_type: IPType | None = None,
    work: str | None = Query(default=None, max_length=255),
    country: str | None = Query(default=None, max_length=2),
    province: str | None = Query(default=None, max_length=100),
    city: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> MapMarkerListResponse:
    marker_set = MapDataService(db).list_marker_set(_filters(ip_type, work, country, province, city))
    return MapMarkerListResponse(
        items=[MapMarkerResponse(**marker.__dict__) for marker in marker_set.markers],
        truncated=marker_set.truncated,
        limit=marker_set.limit,
    )
