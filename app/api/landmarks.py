from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import IPType
from app.schemas.catalog import LandmarkCatalogItem, LandmarkDetailResponse, LandmarkListResponse
from app.services.landmark_catalog import CatalogFilters, CatalogNotFound, LandmarkCatalogService

router = APIRouter(prefix="/api/v1/landmarks", tags=["landmarks"])


def _filters(
    ip_type: IPType | None = None,
    work: str | None = None,
    country: str | None = None,
    province: str | None = None,
    city: str | None = None,
    landmark: str | None = None,
    query: str | None = None,
) -> CatalogFilters:
    return CatalogFilters.from_values(ip_type, work, country, province, city, landmark, query)


def _item(entry) -> LandmarkCatalogItem:
    return LandmarkCatalogItem(
        id=entry.id,
        ip_type=entry.ip_type,
        work_title=entry.work_title,
        name=entry.name,
        country_code=entry.country_code,
        country_name=entry.country_name,
        province_name=entry.province_name,
        city_name=entry.city_name,
        description_summary=entry.description_summary,
        updated_at=entry.updated_at,
    )


@router.get("", response_model=LandmarkListResponse)
def list_landmarks(
    ip_type: IPType | None = None,
    work: str | None = Query(default=None, max_length=255),
    country: str | None = Query(default=None, max_length=2),
    province: str | None = Query(default=None, max_length=100),
    city: str | None = Query(default=None, max_length=100),
    landmark: str | None = Query(default=None, max_length=255),
    q: str | None = Query(default=None, max_length=255, description="Fuzzy match landmark name, work title, or aliases."),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> LandmarkListResponse:
    result = LandmarkCatalogService(db).list(_filters(ip_type, work, country, province, city, landmark, q), page, page_size)
    return LandmarkListResponse(items=[_item(entry) for entry in result.items], total=result.total, page=result.page, page_size=result.page_size)


@router.get("/{landmark_id}", response_model=LandmarkDetailResponse)
def get_landmark(landmark_id: int, db: Session = Depends(get_db)) -> LandmarkDetailResponse:
    try:
        entry = LandmarkCatalogService(db).get_detail(landmark_id)
    except CatalogNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    item = _item(entry)
    return LandmarkDetailResponse(
        **item.model_dump(),
        normalized_address=entry.normalized_address,
        district_name=entry.district_name,
        description=entry.description,
        transit_text=entry.transit_text,
        sources=list(entry.sources),
        disclaimer="地标与交通信息仅供行前参考，请以现场公告和官方渠道为准。",
    )
