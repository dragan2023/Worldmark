from datetime import datetime

from pydantic import BaseModel

from app.models.enums import IPType


class MapMarkerResponse(BaseModel):
    id: int
    name: str
    ip_type: IPType
    work_title: str
    latitude: float
    longitude: float
    detail_url: str
    updated_at: datetime


class MapMarkerListResponse(BaseModel):
    items: list[MapMarkerResponse]


class RouteStopResponse(BaseModel):
    stop_order: int
    landmark_id: int
    landmark_name: str
    work_title: str
    normalized_address: str
    transit_text: str | None
    stay_minutes: int | None
    note: str | None
    source_updated_at: datetime | None


class RouteDetailResponse(BaseModel):
    id: int
    title: str
    summary: str | None
    duration_text: str | None
    stops: list[RouteStopResponse]
    disclaimer: str
