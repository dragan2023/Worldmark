from dataclasses import dataclass

from sqlalchemy.orm import Session, selectinload

from app.models.landmark import Landmark
from app.models.location import Location
from app.services.landmark_catalog import CatalogFilters, published_landmark_statement


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


class MapDataService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_markers(self, filters: CatalogFilters) -> tuple[MapMarker, ...]:
        landmarks = self._db.scalars(
            published_landmark_statement(filters)
            .where(Location.latitude.is_not(None), Location.longitude.is_not(None))
            .options(selectinload(Landmark.ip_work), selectinload(Landmark.location))
            .order_by(Landmark.id)
        ).all()
        return tuple(
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
            for landmark in landmarks
        )
