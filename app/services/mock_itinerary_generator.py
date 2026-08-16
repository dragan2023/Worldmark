from dataclasses import dataclass
from datetime import date, timedelta

from app.models.landmark import Landmark


@dataclass(frozen=True)
class PlannedStop:
    landmark_id: int
    time_slot: str
    planned_minutes: int
    selection_reason: str


@dataclass(frozen=True)
class PlannedDay:
    day_number: int
    itinerary_date: date
    summary: str
    stops: tuple[PlannedStop, ...]


class MockItineraryGenerator:
    """Deterministic fallback when the LLM is unavailable."""

    version = "deterministic-v2"

    def generate(
        self,
        candidates: list[Landmark],
        must_visit_ids: list[int],
        start_date: date,
        total_days: int,
        daily_hours: int,
    ) -> tuple[PlannedDay, ...]:
        by_id = {item.id: item for item in candidates}
        ordered_ids = [item_id for item_id in must_visit_ids if item_id in by_id]
        ordered_ids.extend(item.id for item in candidates if item.id not in ordered_ids)
        days: list[PlannedDay] = []
        cursor = 0
        for day_number in range(1, total_days + 1):
            remaining_days = total_days - day_number + 1
            remaining_ids = ordered_ids[cursor:]
            stop_count = (len(remaining_ids) + remaining_days - 1) // remaining_days if remaining_ids else 0
            day_ids = remaining_ids[:stop_count]
            cursor += len(day_ids)
            stop_minutes = max(15, (daily_hours * 60) // max(1, len(day_ids)))
            stops = tuple(
                PlannedStop(
                    landmark_id=item_id,
                    time_slot=f"{9 + (index * stop_minutes) // 60:02d}:{(index * stop_minutes) % 60:02d}",
                    planned_minutes=stop_minutes,
                    selection_reason="来自已发布、已核验的 IP 地标候选集，并按出行条件和游览时长安排。",
                )
                for index, item_id in enumerate(day_ids)
            )
            days.append(
                PlannedDay(
                    day_number=day_number,
                    itinerary_date=start_date + timedelta(days=day_number - 1),
                    summary="围绕已选 IP 地标的建议游览顺序；交通、营业和预约信息请在出发前确认。",
                    stops=stops,
                )
            )
        return tuple(days)
