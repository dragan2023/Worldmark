"""地图点位数据。

上限 1000 个点位：超过时按更新顺序截断并返回 ``truncated`` 标记，由前端明确告知
结果范围，而不是静默截断或无限渲染。
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session, selectinload

from app.models.landmark import Landmark
from app.models.location import Location
from app.services.landmark_catalog import CatalogFilters, published_landmark_statement

MAX_MARKERS = 1000


@dataclass(frozen=True)
class MapMarker:
    id: int
    name: str
    ip_type: object
    work_title: str
    latitude: float
    longitude: float
    detail_url: str
    updated_at: object


@dataclass(frozen=True)
class MapMarkerSet:
    markers: tuple[MapMarker, ...]
    truncated: bool
    total_available: int
    limit: int = MAX_MARKERS

class MapDataService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_marker_set(self, filters: CatalogFilters) -> MapMarkerSet:
        statement = (
            published_landmark_statement(filters)
            .where(Location.latitude.is_not(None), Location.longitude.is_not(None))
            .options(selectinload(Landmark.ip_work), selectinload(Landmark.location))
            .order_by(Landmark.id)
        )
        landmarks = self._db.scalars(statement.limit(MAX_MARKERS + 1)).all()
        truncated = len(landmarks) > MAX_MARKERS
        selected = landmarks[:MAX_MARKERS]
        markers = tuple(
            MapMarker(
                id=landmark.id,
                name=landmark.name,
                ip_type=landmark.ip_work.ip_type,
                work_title=landmark.ip_work.title,
                latitude=landmark.location.latitude,
                longitude=landmark.location.longitude,
                detail_url=f"/landmarks/{landmark.id}",
                updated_at=landmark.updated_at,
            )
            for landmark in selected
        )
        return MapMarkerSet(
            markers=markers, truncated=truncated, total_available=len(markers), limit=MAX_MARKERS
        )

    def list_markers(self, filters: CatalogFilters) -> tuple[MapMarker, ...]:
        return self.list_marker_set(filters).markers
