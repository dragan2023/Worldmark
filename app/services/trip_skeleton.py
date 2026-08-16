"""Build the deterministic city-and-overnight skeleton before travel data is queried."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class CitySegment:
    city: str
    start_date: date
    days: int
    nights: int

    def as_dict(self) -> dict:
        return {
            "city": self.city,
            "start_date": self.start_date,
            "days": self.days,
            "nights": self.nights,
        }


class TripSkeletonBuilder:
    """Allocate each travel day to a city before calling external travel services."""

    version = "trip-skeleton-v1"

    def build(self, candidates, must_visit_ids: list[int], start_date: date, day_count: int) -> tuple[CitySegment, ...]:
        city_by_id = {
            item.id: item.location.city_name
            for item in candidates
            if item.location and item.location.city_name
        }
        required_cities: list[str] = []
        for landmark_id in must_visit_ids:
            city = city_by_id.get(landmark_id)
            if city and city not in required_cities:
                required_cities.append(city)
        if not required_cities:
            required_cities = list(dict.fromkeys(city_by_id.values()))[:1]
        if not required_cities:
            return ()

        # The candidate count makes extra days go to the denser city cluster,
        # while the required landmark count wins ties.  City order remains the
        # user's selected must-visit order so routes are deterministic.
        candidate_counts = Counter(city_by_id.values())
        required_counts = Counter(city_by_id.get(landmark_id) for landmark_id in must_visit_ids)
        days_by_city = {city: 1 for city in required_cities}
        for _ in range(max(0, day_count - len(required_cities))):
            city = max(
                required_cities,
                key=lambda value: (candidate_counts[value] + required_counts[value] * 2) / days_by_city[value],
            )
            days_by_city[city] += 1

        cursor = start_date
        segments: list[CitySegment] = []
        for index, city in enumerate(required_cities):
            days = days_by_city[city]
            # On a segment transition, the traveller sleeps in the current
            # city on its final day and moves the next day.  The final trip day
            # is the return journey, so it has no destination lodging night.
            nights = days if index < len(required_cities) - 1 else max(0, days - 1)
            segments.append(CitySegment(city, cursor, days, nights))
            cursor += timedelta(days=days)
        return tuple(segments)

    @staticmethod
    def city_by_day(segments: tuple[CitySegment, ...], start_date: date) -> dict[int, str]:
        result: dict[int, str] = {}
        for segment in segments:
            first_day = (segment.start_date - start_date).days + 1
            for day_number in range(first_day, first_day + segment.days):
                result[day_number] = segment.city
        return result
