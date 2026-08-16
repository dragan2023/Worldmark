from datetime import datetime

from pydantic import BaseModel, HttpUrl

from app.models.enums import IPType


class LandmarkCatalogItem(BaseModel):
    id: int
    ip_type: IPType
    work_title: str
    name: str
    country_code: str
    country_name: str
    province_name: str | None
    city_name: str | None
    description_summary: str
    updated_at: datetime


class LandmarkListResponse(BaseModel):
    items: list[LandmarkCatalogItem]
    total: int
    page: int
    page_size: int


class LandmarkSourceResponse(BaseModel):
    title: str | None
    publisher: str | None
    url: HttpUrl
    accessed_at: datetime


class LandmarkDetailResponse(LandmarkCatalogItem):
    normalized_address: str
    district_name: str | None
    description: str
    transit_text: str | None
    sources: list[LandmarkSourceResponse]
    disclaimer: str
