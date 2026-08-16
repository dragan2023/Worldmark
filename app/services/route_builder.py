from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import PublicationStatus
from app.models.landmark import Landmark
from app.models.route import Route, RouteStop
from app.models.source import LandmarkSource


class RouteValidationError(ValueError):
    """Raised when an editor attempts to create or publish an invalid static route."""


class RouteUnavailable(ValueError):
    """Raised when a public route has a hidden or unpublished stop."""


@dataclass(frozen=True)
class RouteStopDraft:
    landmark_id: int
    stay_minutes: int | None = None
    note: str | None = None


@dataclass(frozen=True)
class PublicRouteStop:
    stop_order: int
    landmark_id: int
    landmark_name: str
    work_title: str
    normalized_address: str
    transit_text: str | None
    stay_minutes: int | None
    note: str | None
    source_updated_at: object | None


@dataclass(frozen=True)
class PublicRoute:
    id: int
    title: str
    summary: str | None
    duration_text: str | None
    stops: tuple[PublicRouteStop, ...]


class RouteBuilderService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        title: str,
        summary: str | None,
        duration_text: str | None,
        stops: list[RouteStopDraft],
    ) -> Route:
        normalized_title = title.strip()
        if not normalized_title:
            raise RouteValidationError("Route title is required.")
        if len(stops) < 2:
            raise RouteValidationError("A route needs at least two stops.")
        landmark_ids = [stop.landmark_id for stop in stops]
        if len(set(landmark_ids)) != len(landmark_ids):
            raise RouteValidationError("A landmark can appear only once in a route.")
        landmarks = self._load_landmarks(landmark_ids)
        if len(landmarks) != len(landmark_ids) or any(not self._is_public(landmark) for landmark in landmarks.values()):
            raise RouteValidationError("Every route stop must be a published landmark.")

        ordered_landmarks = [landmarks[landmark_id] for landmark_id in landmark_ids]
        work_ids = {landmark.ip_work_id for landmark in ordered_landmarks}
        city_names = {landmark.location.city_name for landmark in ordered_landmarks if landmark.location.city_name}
        same_work = len(work_ids) == 1
        same_city = len(city_names) == 1 and len(city_names) == len({landmark.location.city_name for landmark in ordered_landmarks})
        if not same_work and not same_city:
            raise RouteValidationError("Stops must belong to one IP work or one city.")

        route = Route(
            title=normalized_title,
            summary=summary.strip() if summary else None,
            duration_text=duration_text.strip() if duration_text else None,
            ip_work_id=ordered_landmarks[0].ip_work_id if same_work else None,
            city_name=ordered_landmarks[0].location.city_name if same_city else None,
            status=PublicationStatus.DRAFT,
        )
        self._db.add(route)
        self._db.flush()
        self._db.add_all(
            RouteStop(
                route_id=route.id,
                landmark_id=stop.landmark_id,
                stop_order=index,
                stay_minutes=stop.stay_minutes,
                note=stop.note.strip() if stop.note else None,
            )
            for index, stop in enumerate(stops, start=1)
        )
        self._db.commit()
        self._db.refresh(route)
        return route

    def publish(self, route_id: int) -> Route:
        route = self._load_route(route_id)
        self._ensure_all_stops_public(route)
        route.status = PublicationStatus.PUBLISHED
        self._db.commit()
        self._db.refresh(route)
        return route

    def get_public(self, route_id: int) -> PublicRoute:
        route = self._load_route(route_id)
        if route.status != PublicationStatus.PUBLISHED:
            raise RouteUnavailable("Published route not found.")
        self._ensure_all_stops_public(route)
        return self._to_public(route)

    def preview(self, route_id: int) -> PublicRoute:
        """Render an editor preview without changing a draft route's publication status."""
        route = self._load_route(route_id)
        self._ensure_all_stops_public(route)
        return self._to_public(route)

    @staticmethod
    def _to_public(route: Route) -> PublicRoute:
        stops = tuple(
            PublicRouteStop(
                stop_order=stop.stop_order,
                landmark_id=stop.landmark_id,
                landmark_name=stop.landmark.name,
                work_title=stop.landmark.ip_work.title,
                normalized_address=stop.landmark.location.normalized_address,
                transit_text=stop.landmark.transit_text,
                stay_minutes=stop.stay_minutes,
                note=stop.note,
                source_updated_at=max((item.source.accessed_at for item in stop.landmark.sources if item.source), default=None),
            )
            for stop in sorted(route.stops, key=lambda item: item.stop_order)
        )
        return PublicRoute(route.id, route.title, route.summary, route.duration_text, stops)

    def _load_landmarks(self, landmark_ids: list[int]) -> dict[int, Landmark]:
        landmarks = self._db.scalars(
            select(Landmark)
            .where(Landmark.id.in_(landmark_ids))
            .options(selectinload(Landmark.ip_work), selectinload(Landmark.location))
        ).all()
        return {landmark.id: landmark for landmark in landmarks}

    def _load_route(self, route_id: int) -> Route:
        route = self._db.scalar(
            select(Route)
            .where(Route.id == route_id)
            .options(
                selectinload(Route.stops)
                .selectinload(RouteStop.landmark)
                .selectinload(Landmark.ip_work),
                selectinload(Route.stops)
                .selectinload(RouteStop.landmark)
                .selectinload(Landmark.location),
                selectinload(Route.stops)
                .selectinload(RouteStop.landmark)
                .selectinload(Landmark.sources)
                .selectinload(LandmarkSource.source),
            )
        )
        if route is None:
            raise RouteUnavailable("Route not found.")
        return route

    @staticmethod
    def _is_public(landmark: Landmark) -> bool:
        return landmark.published_at is not None and landmark.ip_work.status == PublicationStatus.PUBLISHED

    def _ensure_all_stops_public(self, route: Route) -> None:
        if len(route.stops) < 2 or any(not self._is_public(stop.landmark) for stop in route.stops):
            raise RouteUnavailable("This route is unavailable because one or more stops are no longer published.")
