"""Reorder a day's stops by nearest-neighbour walking distance.

The optimizer solves a greedy "traveling salesman" pass over each day's stops:
it keeps the first stop fixed (so a required landmark remains the day's
opening stop) and repeatedly appends the closest remaining stop. Distance is
taken from the Amap walking service when available and falls back to a local
haversine estimate so the pipeline stays deterministic and network-free in
tests and when no Amap key is configured.
"""

from dataclasses import replace
from math import asin, cos, radians, sin, sqrt

from app.integrations.amap_web_service import AmapWebService
from app.services.mock_itinerary_generator import PlannedStop

EARTH_RADIUS_METERS = 6371000.0


def haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in meters between two ``(lat, lng)`` points."""
    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(h))


class RouteOptimizer:
    def __init__(self, amap: AmapWebService | None = None) -> None:
        self._amap = amap
        self._cache: dict[tuple[int, int], float] = {}

    def optimize_day(
        self,
        stops: tuple[PlannedStop, ...],
        coords: dict[int, tuple[float, float]],
        start_coord: tuple[float, float] | None = None,
    ) -> tuple[PlannedStop, ...]:
        if len(stops) <= 1:
            return stops
        remaining = list(stops)
        if start_coord is None:
            ordered = [remaining.pop(0)]
        else:
            first_index = self._closest_to_coordinate(remaining, coords, start_coord)
            ordered = [remaining.pop(first_index)] if first_index is not None else [remaining.pop(0)]
        while remaining:
            current = ordered[-1]
            current_coord = coords.get(current.landmark_id)
            if current_coord is None:
                ordered.extend(remaining)
                break
            nearest_index: int | None = None
            nearest_distance: float | None = None
            for index, candidate in enumerate(remaining):
                candidate_coord = coords.get(candidate.landmark_id)
                if candidate_coord is None:
                    continue
                distance = self._distance(current.landmark_id, candidate.landmark_id, current_coord, candidate_coord)
                if nearest_distance is None or distance < nearest_distance:
                    nearest_distance = distance
                    nearest_index = index
            if nearest_index is None:
                ordered.extend(remaining)
                break
            ordered.append(remaining.pop(nearest_index))
        return self._reassign_time_slots(tuple(ordered))

    @staticmethod
    def _closest_to_coordinate(
        stops: list[PlannedStop], coords: dict[int, tuple[float, float]], start_coord: tuple[float, float]
    ) -> int | None:
        candidates = [(index, coords.get(stop.landmark_id)) for index, stop in enumerate(stops)]
        available = [(index, coord) for index, coord in candidates if coord is not None]
        if not available:
            return None
        return min(available, key=lambda pair: haversine_meters(start_coord, pair[1]))[0]

    def _distance(
        self,
        a_id: int,
        b_id: int,
        a_coord: tuple[float, float],
        b_coord: tuple[float, float],
    ) -> float:
        key = (min(a_id, b_id), max(a_id, b_id))
        if key not in self._cache:
            self._cache[key] = self._walking_or_haversine(a_coord, b_coord)
        return self._cache[key]

    def _walking_or_haversine(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        if self._amap is not None:
            try:
                result = self._amap.walking_distance(f"{a[1]},{a[0]}", f"{b[1]},{b[0]}")
                if result and result.get("distance_meters"):
                    return float(result["distance_meters"])
            except Exception:
                pass
        return haversine_meters(a, b)

    @staticmethod
    def _reassign_time_slots(stops: tuple[PlannedStop, ...]) -> tuple[PlannedStop, ...]:
        cursor_minutes = 9 * 60
        result: list[PlannedStop] = []
        for stop in stops:
            hours, minutes = divmod(cursor_minutes, 60)
            result.append(replace(stop, time_slot=f"{hours:02d}:{minutes:02d}"))
            cursor_minutes += stop.planned_minutes
        return tuple(result)
