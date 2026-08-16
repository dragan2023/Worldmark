"""Build an executable itinerary from choices explicitly confirmed by the traveler."""

from collections import defaultdict
from datetime import timedelta

from app.schemas.itinerary import ItineraryCreateRequest
from app.services.mock_itinerary_generator import PlannedDay, PlannedStop
from app.services.route_optimizer import haversine_meters


class ConfirmedItineraryBuilder:
    version = "confirmed-itinerary-v1"

    def generate(self, request: ItineraryCreateRequest, candidates) -> tuple[tuple[PlannedDay, ...], dict]:
        by_id = {item.id: item for item in candidates}
        traveler_count = request.traveler_count
        landmark_costs = {item.landmark_id: item.price * traveler_count for item in request.landmark_costs}
        city_by_id = {item.id: item.location.city_name if item.location else "\u5f85\u786e\u8ba4" for item in candidates}
        selected_ids = list(dict.fromkeys(item_id for item_id in request.must_visit_landmark_ids if item_id in by_id))
        day_count = (request.end_date - request.start_date).days + 1
        plan_cities = list(dict.fromkeys(city_by_id[item_id] for item_id in selected_ids)) or ["\u5f85\u786e\u8ba4"]

        required_by_day: dict[int, list[int]] = defaultdict(list)
        for index, item_id in enumerate(selected_ids):
            required_by_day[(index % day_count) + 1].append(item_id)

        city_by_day = {
            day_number: city_by_id[required_by_day[day_number][0]]
            if required_by_day[day_number]
            else plan_cities[(day_number - 1) % len(plan_cities)]
            for day_number in range(1, day_count + 1)
        }
        day_numbers_by_city: dict[str, list[int]] = defaultdict(list)
        for day_number, city in city_by_day.items():
            day_numbers_by_city[city].append(day_number)

        lodging_by_city = {item.city: item for item in request.confirmed_lodgings}
        scenic_by_city: dict[str, list] = defaultdict(list)
        food_by_city: dict[str, list] = defaultdict(list)
        for item in request.confirmed_items:
            (scenic_by_city if item.item_type == "scenic" else food_by_city)[item.city].append(item)
        scenic_by_day: dict[int, list] = defaultdict(list)
        food_by_day: dict[int, list] = defaultdict(list)
        for city, items in scenic_by_city.items():
            matching_days = day_numbers_by_city.get(city) or list(city_by_day)
            for index, item in enumerate(items):
                scenic_by_day[matching_days[index % len(matching_days)]].append(item)
        for city, items in food_by_city.items():
            matching_days = day_numbers_by_city.get(city) or list(city_by_day)
            for index, item in enumerate(items):
                food_by_day[matching_days[index % len(matching_days)]].append(item)

        nights_by_city: dict[str, int] = defaultdict(int)
        for day_number, city in city_by_day.items():
            if day_number < day_count:
                nights_by_city[city] += 1

        days: list[PlannedDay] = []
        contexts: dict[int, dict] = {}
        supplemental_by_day: dict[int, list[dict]] = {}
        for day_number in range(1, day_count + 1):
            day_date = request.start_date + timedelta(days=day_number - 1)
            city = city_by_day[day_number]
            ordered_ids = self._order_ids(required_by_day[day_number], by_id, lodging_by_city.get(city))
            stops, supplemental, food_events = self._schedule_day(
                ordered_ids,
                scenic_by_day[day_number],
                food_by_day[day_number],
                by_id,
                city,
                landmark_costs,
                traveler_count,
            )
            supplemental_by_day[day_number] = supplemental
            contexts[day_number] = {
                "city": city,
                "lodging": self._lodging_context(lodging_by_city.get(city), overnight=day_number < day_count),
                "confirmed_food_events": food_events,
                "landmark_costs": {str(item_id): landmark_costs.get(item_id, 0) for item_id in ordered_ids},
                "intercity_transport": self._transport_for_date(request, day_date),
            }
            days.append(
                PlannedDay(
                    day_number,
                    day_date,
                    f"{city}\u5df2\u786e\u8ba4\u884c\u7a0b\uff1a\u666f\u70b9\u3001\u9910\u996e\u548c\u4f4f\u5bbf\u5747\u6765\u81ea\u7528\u6237\u9009\u62e9\u3002",
                    tuple(stops),
                )
            )
        return tuple(days), {
            "travel_contexts": contexts,
            "supplemental": supplemental_by_day,
            "budget": self._budget(request, nights_by_city),
        }

    def _schedule_day(self, ordered_ids, scenic_items, food_items, by_id, city, landmark_costs, traveler_count):
        cursor = 9 * 60
        stops: list[PlannedStop] = []
        for item_id in ordered_ids:
            stops.append(
                PlannedStop(
                    item_id,
                    self._clock(cursor),
                    120,
                    "\u7528\u6237\u5df2\u786e\u8ba4\u7684 IP \u5730\u6807\uff1b\u6309\u4f4f\u5bbf\u951a\u70b9\u548c\u76f8\u90bb\u987a\u5e8f\u7f16\u6392\u3002",
                )
            )
            cursor += 120

        supplemental: list[dict] = []
        for item in scenic_items:
            start = self._clock(cursor)
            duration = 120
            cursor += duration
            supplemental.append(
                {
                    "type": "\u5df2\u786e\u8ba4\u8865\u5145\u666f\u70b9",
                    "name": item.name,
                    "city": city,
                    "price": item.price * traveler_count,
                    "address": item.address,
                    "note": item.note or "\u7528\u6237\u5df2\u786e\u8ba4\u8865\u5145\u666f\u70b9",
                    "time_slot": start,
                    "planned_minutes": duration,
                    "end_time": self._clock(cursor),
                }
            )

        food_events: list[dict] = []
        for item in food_items:
            cursor += 30
            start = self._clock(cursor)
            duration = 60
            cursor += duration
            food_events.append(
                {
                    "time_slot": start,
                    "planned_minutes": duration,
                    "end_time": self._clock(cursor),
                    "name": item.name,
                    "price": item.price,
                    "address": item.address,
                    "note": item.note or "\u7528\u6237\u5df2\u786e\u8ba4\u9910\u996e",
                }
            )
        return stops, supplemental, food_events

    @staticmethod
    def _clock(minutes: int) -> str:
        minutes %= 24 * 60
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    @staticmethod
    def _order_ids(ids, by_id, lodging):
        if len(ids) < 2:
            return ids
        start = getattr(lodging, "coordinate", None) if lodging and lodging.address else None
        coordinates = {
            item_id: (by_id[item_id].location.latitude, by_id[item_id].location.longitude)
            for item_id in ids
            if by_id[item_id].location
            and by_id[item_id].location.latitude is not None
            and by_id[item_id].location.longitude is not None
        }
        remaining = list(ids)
        if start and coordinates:
            first = min(
                (item_id for item_id in remaining if item_id in coordinates),
                key=lambda item_id: haversine_meters(start, coordinates[item_id]),
                default=remaining[0],
            )
            ordered = [first]
            remaining.remove(first)
        else:
            ordered = [remaining.pop(0)]
        while remaining:
            current = coordinates.get(ordered[-1])
            if not current:
                ordered.extend(remaining)
                break
            next_id = min(
                (item_id for item_id in remaining if item_id in coordinates),
                key=lambda item_id: haversine_meters(current, coordinates[item_id]),
                default=remaining[0],
            )
            ordered.append(next_id)
            remaining.remove(next_id)
        return ordered

    @staticmethod
    def _lodging_context(lodging, *, overnight: bool):
        if lodging is None:
            return {"mode": "none"}
        return {
            "mode": "confirmed",
            "name": lodging.name,
            "address": lodging.address,
            "reference_price_per_night": lodging.nightly_price,
            "overnight": overnight,
            "status": "\u7528\u6237\u5df2\u786e\u8ba4",
            "note": "\u5f53\u65e5\u4ece\u5df2\u786e\u8ba4\u4f4f\u5bbf\u51fa\u53d1\uff0c\u5e76\u5728\u665a\u95f4\u8fd4\u56de\u3002",
        }

    @staticmethod
    def _transport_for_date(request, day_date):
        return [
            {
                "label": item.leg_label,
                "from": item.departure,
                "to": item.arrival,
                "date": item.travel_date.isoformat(),
                "mode": item.mode,
                "option_id": item.option_id,
                "seat": item.seat,
                "unit_price": item.price,
                "traveler_count": request.traveler_count,
                "price": item.price * request.traveler_count,
                "note": "\u7528\u6237\u5df2\u786e\u8ba4\u5927\u4ea4\u901a\uff1b\u8868\u5185\u4e3a\u5168\u90e8\u51fa\u884c\u4eba\u6570\u5408\u8ba1\u3002",
            }
            for item in request.confirmed_transports
            if item.travel_date == day_date
        ]

    @staticmethod
    def _budget(request, nights_by_city):
        transportation = sum(item.price * request.traveler_count for item in request.confirmed_transports)
        lodging = sum(item.nightly_price * nights_by_city.get(item.city, 0) for item in request.confirmed_lodgings)
        scenic = sum(item.price * request.traveler_count for item in request.landmark_costs)
        scenic += sum(item.price * request.traveler_count for item in request.confirmed_items if item.item_type == "scenic")
        food = sum(item.price for item in request.confirmed_items if item.item_type == "food")
        total = transportation + lodging + scenic + food
        return {
            "budget_amount": request.budget_amount,
            "estimated_amount": total,
            "status": "\u5df2\u6309\u7528\u6237\u786e\u8ba4\u7684\u4ea4\u901a\u3001\u4f4f\u5bbf\u3001\u666f\u70b9\u548c\u9910\u996e\u6838\u7b97\u3002",
            "breakdown": {
                "intercity_transport": transportation,
                "lodging": lodging,
                "scenic": scenic,
                "food": food,
            },
        }
