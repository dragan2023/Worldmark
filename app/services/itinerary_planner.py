from datetime import UTC, datetime, timedelta
from dataclasses import replace
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.integrations.amap_web_service import AmapWebService
from app.integrations.deepseek_client import DeepSeekClient
from app.integrations.meituan_travel_mcp import MeituanTravelMcp
from app.models.enums import ItineraryStatus, VerificationStatus
from app.models.itinerary import Itinerary, ItineraryDay, ItineraryStop
from app.models.landmark import Landmark
from app.models.location import Location
from app.models.source import LandmarkSource
from app.schemas.itinerary import ItineraryCreateRequest, ItineraryDayEdit
from app.services.deepseek_itinerary_generator import DeepSeekItineraryGenerator, ItineraryGenerationError
from app.services.confirmed_itinerary import ConfirmedItineraryBuilder
from app.services.itinerary_validator import ItineraryValidationError, ItineraryValidator
from app.services.landmark_catalog import CatalogFilters, published_landmark_statement
from app.services.mock_itinerary_generator import MockItineraryGenerator, PlannedDay
from app.services.meituan_itinerary_parser import MeituanItineraryParser
from app.services.route_optimizer import RouteOptimizer
from app.services.trip_skeleton import TripSkeletonBuilder
from app.services.travel_enrichment import TravelEnrichmentService
from app.services.travel_price_completion import TravelPriceCompletionService


class ItineraryNotFound(ValueError):
    """Raised when an itinerary is absent or belongs to another member."""


class ItineraryPlannerService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._validator = ItineraryValidator()
        self._mock_generator = MockItineraryGenerator()
        self._generator = self._build_generator()
        self._confirmed_generator = ConfirmedItineraryBuilder()
        self._meituan_parser = MeituanItineraryParser()
        self._trip_skeleton = TripSkeletonBuilder()
        self._price_completion = self._build_price_completion()

    def _build_generator(self):
        key = self._settings.deepseek_api_key.get_secret_value() if self._settings.deepseek_api_key else None
        if not key:
            return self._mock_generator
        client = DeepSeekClient(
            key,
            self._settings.deepseek_base_url,
            self._settings.deepseek_model,
            thinking=self._settings.deepseek_thinking,
        )
        return DeepSeekItineraryGenerator(client)

    def _build_optimizer(self) -> RouteOptimizer:
        key = self._settings.amap_web_service_api_key.get_secret_value() if self._settings.amap_web_service_api_key else None
        if key:
            return RouteOptimizer(AmapWebService(key))
        return RouteOptimizer(None)

    def _build_travel_enrichment(self) -> TravelEnrichmentService:
        effective_token = self._settings.effective_meituan_travel_token
        token = effective_token.get_secret_value() if effective_token else None
        bocha_key = self._settings.bocha_api_key.get_secret_value() if self._settings.bocha_api_key else None
        amap_key = self._settings.amap_web_service_api_key.get_secret_value() if self._settings.amap_web_service_api_key else None
        return TravelEnrichmentService(
            MeituanTravelMcp(token) if token else None,
            bocha_api_key=bocha_key,
            amap=AmapWebService(amap_key) if amap_key else None,
        )

    def _build_price_completion(self) -> TravelPriceCompletionService:
        effective_token = self._settings.effective_meituan_travel_token
        token = effective_token.get_secret_value() if effective_token else None
        amap_key = self._settings.amap_web_service_api_key.get_secret_value() if self._settings.amap_web_service_api_key else None
        bocha_key = self._settings.bocha_api_key.get_secret_value() if self._settings.bocha_api_key else None
        return TravelPriceCompletionService(
            MeituanTravelMcp(token) if token else None,
            amap=AmapWebService(amap_key) if amap_key else None,
            bocha_api_key=bocha_key,
        )

    def _optimize_routes(
        self,
        planned_days: tuple[PlannedDay, ...],
        candidates: list[Landmark],
        lodging_coordinate: tuple[float, float] | None = None,
    ) -> tuple[PlannedDay, ...]:
        coords = {
            item.id: (item.location.latitude, item.location.longitude)
            for item in candidates
            if item.location is not None and item.location.latitude is not None and item.location.longitude is not None
        }
        optimizer = self._build_optimizer()
        return tuple(
            replace(day, stops=optimizer.optimize_day(day.stops, coords, start_coord=lodging_coordinate))
            for day in planned_days
        )

    def _lodging_coordinate(self, request: ItineraryCreateRequest, destination_city: str | None) -> tuple[float, float] | None:
        if request.lodging_mode != "booked" or not (request.lodging_address or request.lodging_name):
            return None
        key = self._settings.amap_web_service_api_key.get_secret_value() if self._settings.amap_web_service_api_key else None
        if not key:
            return None
        try:
            value = AmapWebService(key).geocode(request.lodging_address or request.lodging_name or "", request.lodging_city or destination_city)
            if not value:
                return None
            lng, lat = (float(part) for part in value.split(",", 1))
            return lat, lng
        except Exception:
            return None

    def _generate_with_fallback(
        self,
        candidates: list[Landmark],
        must_visit_ids: list[int],
        start_date,
        day_count: int,
        daily_hours: int,
        planning_context: dict | None = None,
    ) -> tuple[tuple[PlannedDay, ...], str]:
        if self._generator is self._mock_generator:
            return self._mock_generator.generate(candidates, must_visit_ids, start_date, day_count, daily_hours), self._mock_generator.version
        try:
            return self._generator.generate(
                candidates, must_visit_ids, start_date, day_count, daily_hours, planning_context=planning_context
            ), self._generator.version
        except ItineraryGenerationError:
            return self._mock_generator.generate(candidates, must_visit_ids, start_date, day_count, daily_hours), self._mock_generator.version

    def create(self, user_id: int, request: ItineraryCreateRequest) -> Itinerary:
        day_count = (request.end_date - request.start_date).days + 1
        candidates = self._load_candidates(request)
        if not candidates:
            raise ItineraryValidationError("No published and verified domestic landmarks match the selected conditions.")
        candidate_ids = {item.id for item in candidates}
        if not set(request.must_visit_landmark_ids).issubset(candidate_ids):
            raise ItineraryValidationError("A required landmark is outside the current published candidate set.")
        candidates = [item for item in candidates if item.id not in set(request.excluded_landmark_ids)]
        if not candidates:
            raise ItineraryValidationError("All published candidates were excluded.")
        required_cities = [
            item.location.city_name for item in candidates
            if item.id in request.must_visit_landmark_ids and item.location and item.location.city_name
        ]
        if len(set(required_cities)) > day_count:
            raise ItineraryValidationError("The required landmarks span more cities than available travel days.")

        primary_location = next((item.location for item in candidates if item.id in request.must_visit_landmark_ids), candidates[0].location)
        destination_city = primary_location.city_name if primary_location else None
        city_plan = self._city_plan(candidates, request.must_visit_landmark_ids, request.start_date, day_count)
        started_at = datetime.now(UTC)
        if request.confirmed_plan:
            planned_days, confirmed = self._confirmed_generator.generate(request, candidates)
            planned_days = self._apply_city_skeleton(planned_days, candidates, city_plan, request.start_date)
            lodging_coordinate = self._confirmed_lodging_coordinate(request, destination_city)
            supplemental_by_day = confirmed["supplemental"]
            travel_context_by_day = confirmed["travel_contexts"]
            city_by_day = self._trip_skeleton.city_by_day(
                tuple(self._trip_skeleton.build(candidates, request.must_visit_landmark_ids, request.start_date, day_count)),
                request.start_date,
            )
            travel_context_by_day = {
                number: {**context, "city": city_by_day.get(number, context.get("city"))}
                for number, context in travel_context_by_day.items()
            }
            lodging_reference = {
                "status": "用户已确认",
                "cities": [item.model_dump() for item in request.confirmed_lodgings],
            }
            transport_reference = {
                "status": "用户已确认",
                "legs": [item.model_dump(mode="json") for item in request.confirmed_transports],
            }
            budget_summary = confirmed["budget"]
            if request.meituan_plan_content:
                structured_plan = self._meituan_parser.parse(
                    request.meituan_plan_content,
                    start_date=request.start_date,
                    day_count=day_count,
                    default_city=destination_city or "待确认",
                )
                if structured_plan.items:
                    structured_plan = self._align_plan_cities(structured_plan, city_plan, request.start_date)
                    structured_plan = self._price_completion.complete_transport(
                        structured_plan, request, destination_city or "待确认", city_plan=city_plan
                    )
                    structured_plan = self._price_completion.complete_lodging(
                        structured_plan, request, destination_city or "待确认", city_plan=city_plan
                    )
                    structured_plan = self._price_completion.complete(structured_plan)
                    planned_days, supplemental_by_day, travel_context_by_day = self._merge_meituan_plan(
                        structured_plan, planned_days, supplemental_by_day, travel_context_by_day
                    )
                    lodging_reference = self._meituan_lodging_reference(structured_plan)
                    transport_reference = self._meituan_transport_reference(structured_plan)
                    budget_summary = {**structured_plan.budget, "budget_amount": request.budget_amount}
                    generator_version = "meituan-skill-v1"
                else:
                    generator_version = self._confirmed_generator.version
                    budget_summary = {**budget_summary, "meituan_plan_warning": structured_plan.warning}
            else:
                generator_version = self._confirmed_generator.version
        else:
            planned_days, generator_version = self._generate_with_fallback(
                candidates,
                request.must_visit_landmark_ids,
                request.start_date,
                day_count,
                request.daily_hours,
                planning_context=None,
            )
            planned_days = self._cluster_days_by_city(planned_days, candidates, request.must_visit_landmark_ids, request.daily_hours)
            lodging_coordinate = self._lodging_coordinate(request, destination_city)
            supplemental_by_day = {}
            travel_context_by_day = self._base_day_contexts(request, planned_days, candidates, destination_city)
            lodging_reference = {"status": "未确认", "note": "请参考美团酒旅官方建议后自行确认住宿。"}
            transport_reference = {"status": "未确认", "note": "请参考美团酒旅官方建议后自行确认交通。", "legs": []}
            budget_summary = {"budget_amount": request.budget_amount, "estimated_amount": None, "status": "未写入未确认的动态价格", "breakdown": {}}
        planned_days = self._optimize_routes(planned_days, candidates, lodging_coordinate)
        self._validator.validate_days(planned_days, candidate_ids, day_count)
        itinerary = Itinerary(
            user_id=user_id,
            ip_work_id=candidates[0].ip_work_id if len({item.ip_work_id for item in candidates}) == 1 else None,
            ip_type=request.ip_type,
            title=(request.title or self._default_title(destination_city, day_count)).strip(),
            destination_country="CN",
            destination_province=primary_location.province_name if primary_location else None,
            destination_city=destination_city,
            start_date=request.start_date,
            end_date=request.end_date,
            daily_hours=request.daily_hours,
            companions=request.companions.strip() if request.companions else None,
            walking_preference=None,
            budget_tier=None,
            origin_city=request.origin_city.strip(),
            return_city=(request.return_city or request.origin_city).strip(),
            traveler_count=request.traveler_count,
            budget_amount=request.budget_amount,
            transport_preference=request.transport_preference,
            auto_fill_nearby=request.auto_fill_nearby,
            interests=request.interests,
            lodging_mode=request.lodging_mode,
            lodging_name=request.lodging_name.strip() if request.lodging_name else None,
            lodging_address=request.lodging_address.strip() if request.lodging_address else None,
            lodging_city=request.lodging_city.strip() if request.lodging_city else destination_city,
            lodging_reference=lodging_reference,
            transport_reference=transport_reference,
            budget_summary=budget_summary,
            free_text=request.free_text.strip() if request.free_text else None,
            input_snapshot=request.model_dump(mode="json"),
            candidate_landmark_ids=sorted(candidate_ids),
            used_landmark_ids=[stop.landmark_id for day in planned_days for stop in day.stops],
            generator_version=generator_version,
            prompt_version=None,
            status=ItineraryStatus.RUNNING,
            generation_candidate_count=len(candidates),
        )
        self._db.add(itinerary)
        self._db.flush()
        self._apply_days(itinerary, planned_days, supplemental_by_day, travel_context_by_day)
        itinerary.status = ItineraryStatus.SUCCEEDED
        itinerary.generation_duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        self._db.commit()
        return self.get_owned(user_id, itinerary.id)

    def preview_choices(self, request: ItineraryCreateRequest) -> dict:
        """Return selections for the confirmation screen; nothing is persisted."""
        candidates = self._load_candidates(request)
        if not candidates:
            raise ItineraryValidationError("No published and verified domestic landmarks match the selected conditions.")
        candidate_ids = {item.id for item in candidates}
        if not set(request.must_visit_landmark_ids).issubset(candidate_ids):
            raise ItineraryValidationError("A required landmark is outside the current published candidate set.")
        day_count = (request.end_date - request.start_date).days + 1
        city_plan = self._city_plan(candidates, request.must_visit_landmark_ids, request.start_date, day_count)
        travel_enrichment = self._build_travel_enrichment()
        meituan_plan = travel_enrichment.plan(request, city_plan, self._landmark_names_by_city(candidates))
        landmarks = [
            {
                "id": item.id,
                "name": item.name,
                "city": item.location.city_name if item.location else None,
                "address": item.location.normalized_address if item.location else None,
                "required": item.id in request.must_visit_landmark_ids,
            }
            for item in candidates
        ]
        return {
            "city_plan": [{**row, "start_date": row["start_date"].isoformat()} for row in city_plan],
            "selection_limits": self._selection_limits(request),
            "landmarks": landmarks,
            "meituan_plan": {
                "status": meituan_plan.status,
                "content": meituan_plan.content,
                "source": meituan_plan.source,
                "queried_at": meituan_plan.queried_at.isoformat() if meituan_plan.queried_at else None,
                "warning": meituan_plan.warning,
            },
        }

    def finalize(self, user_id: int, request: ItineraryCreateRequest) -> Itinerary:
        """Keep supplier output backstage and persist only the normalized itinerary."""
        preview = self.preview_choices(request)
        plan = preview["meituan_plan"]
        if plan["status"] != "available" or not plan["content"]:
            raise ItineraryValidationError(plan["warning"] or "暂时无法完成行程规划，请稍后重试。")
        final_request = request.model_copy(
            update={
                "confirmed_plan": True,
                "meituan_plan_content": plan["content"],
                "confirmed_transports": [],
                "confirmed_lodgings": [],
                "confirmed_items": [],
                "landmark_costs": [],
            }
        )
        return self.create(user_id, final_request)

    @staticmethod
    def _selection_limits(request: ItineraryCreateRequest) -> dict[str, int]:
        day_count = (request.end_date - request.start_date).days + 1
        attraction_capacity = max(day_count, (request.daily_hours // 3) * day_count)
        required_landmark_count = len(set(request.must_visit_landmark_ids))
        supplemental_scenic_max = max(0, attraction_capacity - required_landmark_count)
        food_max = day_count * 3
        return {
            "required_landmark_count": required_landmark_count,
            "attraction_total_target": attraction_capacity,
            "supplemental_scenic_needed": supplemental_scenic_max,
            "supplemental_scenic_max": supplemental_scenic_max,
            "food_needed": food_max,
            "food_max": food_max,
            "daily_attraction_capacity": max(1, request.daily_hours // 3),
        }

    @staticmethod
    def _base_day_contexts(
        request: ItineraryCreateRequest,
        planned_days: tuple[PlannedDay, ...],
        candidates: list[Landmark],
        destination_city: str | None,
    ) -> dict[int, dict]:
        city_by_id = {item.id: item.location.city_name if item.location else destination_city for item in candidates}
        result: dict[int, dict] = {}
        previous_city = request.origin_city
        for day in planned_days:
            city = city_by_id.get(day.stops[0].landmark_id, destination_city) if day.stops else destination_city
            legs = []
            if previous_city and city and previous_city != city:
                legs.append({
                    "label": "去程" if day.day_number == 1 else "城市间移动",
                    "from": previous_city,
                    "to": city,
                    "date": day.itinerary_date.isoformat(),
                    "note": "请参考美团酒旅官方建议后自行确认班次。",
                })
            result[day.day_number] = {
                "city": city,
                "lodging": {"mode": "none", "note": "请参考美团酒旅官方建议后自行确认住宿。"},
                "intercity_transport": legs,
                "confirmed_food_events": [],
            }
            previous_city = city
        return result

    @staticmethod
    def _merge_meituan_plan(
        structured_plan,
        planned_days: tuple[PlannedDay, ...],
        supplemental_by_day: dict[int, list[dict]],
        contexts: dict[int, dict],
    ):
        """Keep IP stops for the map while rendering the Skill response as the daily plan."""
        supplemental = {day: list(items) for day, items in supplemental_by_day.items()}
        merged_contexts = {
            day: {**value, "meituan_items": list(value.get("meituan_items", []))}
            for day, value in contexts.items()
        }
        for item in structured_plan.items:
            context = merged_contexts[item.day_number]
            context["city"] = item.city or context.get("city")
            time_slot, end_time, planned_minutes = ItineraryPlannerService._split_time_range(item.time_slot)
            row = {
                "type": "行程安排",
                "name": item.name,
                "city": item.city,
                "time_slot": time_slot,
                "end_time": end_time,
                "planned_minutes": planned_minutes,
                "price": item.amount or 0,
                "price_missing": item.amount is None,
                "price_source": (structured_plan.budget.get("price_sources") or {}).get(f"{item.day_number}:{item.name}"),
                "transport": item.transport,
                "note": item.note,
                "category": item.category,
                "source": "后台规划服务",
            }
            supplemental.setdefault(item.day_number, []).append(row)
            context["meituan_items"].append(row)

        item_counts = {day: len(context.get("meituan_items", [])) for day, context in merged_contexts.items()}
        display_days = tuple(
            replace(
                day,
                summary=(
                    f"当日已整理 {item_counts.get(day.day_number, 0)} 项安排，"
                    "费用已计入顶部预算汇总；未标价项目会单独提示。"
                    if item_counts.get(day.day_number, 0)
                    else day.summary
                ),
            )
            for day in planned_days
        )
        return display_days, supplemental, merged_contexts

    def reprocess_meituan_plan(self, user_id: int, itinerary_id: int) -> Itinerary:
        """Rebuild a legacy itinerary from its stored official Skill response."""
        itinerary = self.get_owned(user_id, itinerary_id)
        raw_content = (itinerary.input_snapshot or {}).get("meituan_plan_content")
        if not raw_content:
            raise ItineraryValidationError("该行程没有保存可重新整理的美团酒旅方案。")
        day_count = (itinerary.end_date - itinerary.start_date).days + 1
        structured_plan = self._meituan_parser.parse(
            raw_content,
            start_date=itinerary.start_date,
            day_count=day_count,
            default_city=itinerary.destination_city or "待确认",
        )
        if not structured_plan.items:
            raise ItineraryValidationError(structured_plan.warning or "美团酒旅方案无法标准化。")
        candidates = self._db.scalars(
            select(Landmark)
            .where(Landmark.id.in_(itinerary.candidate_landmark_ids))
            .options(selectinload(Landmark.location))
        ).all()
        city_plan = self._city_plan(
            candidates,
            (itinerary.input_snapshot or {}).get("must_visit_landmark_ids", []),
            itinerary.start_date,
            day_count,
        )
        structured_plan = self._align_plan_cities(structured_plan, city_plan, itinerary.start_date)
        reprocess_request = type("StoredRequest", (), {
            "start_date": itinerary.start_date,
            "end_date": itinerary.end_date,
            "origin_city": itinerary.origin_city,
            "return_city": itinerary.return_city,
            "traveler_count": itinerary.traveler_count,
        })()
        structured_plan = self._price_completion.complete_transport(
            structured_plan, reprocess_request, itinerary.destination_city or "待确认", city_plan=city_plan
        )
        structured_plan = self._price_completion.complete_lodging(
            structured_plan, reprocess_request, itinerary.destination_city or "待确认", city_plan=city_plan
        )
        structured_plan = self._price_completion.complete(structured_plan)

        base_days = tuple(
            PlannedDay(day.day_number, day.itinerary_date, day.summary or "", tuple())
            for day in sorted(itinerary.days, key=lambda value: value.day_number)
        )
        base_supplemental = {day.day_number: [] for day in itinerary.days}
        base_contexts = {
            day.day_number: {
                "city": (day.travel_context or {}).get("city") or itinerary.destination_city or "待确认",
                "lodging": (day.travel_context or {}).get("lodging") or {"mode": "none"},
                "intercity_transport": [],
                "confirmed_food_events": [],
            }
            for day in itinerary.days
        }
        display_days, supplemental, contexts = self._merge_meituan_plan(
            structured_plan, base_days, base_supplemental, base_contexts
        )
        by_number = {day.day_number: day for day in itinerary.days}
        for display_day in display_days:
            stored_day = by_number[display_day.day_number]
            stored_day.summary = display_day.summary
            stored_day.supplemental_items = supplemental[display_day.day_number]
            stored_day.travel_context = contexts[display_day.day_number]
        itinerary.lodging_reference = self._meituan_lodging_reference(structured_plan)
        itinerary.transport_reference = self._meituan_transport_reference(structured_plan)
        itinerary.budget_summary = {**structured_plan.budget, "budget_amount": itinerary.budget_amount}
        itinerary.generator_version = "meituan-skill-v1"
        itinerary.version += 1
        self._db.commit()
        return self.get_owned(user_id, itinerary_id)

    @staticmethod
    def _split_time_range(value: str) -> tuple[str, str | None, int]:
        """Turn `09:00-11:00` into displayable start/end values without inventing costs."""
        normalized = (value or "待确认").replace("－", "-").replace("—", "-").replace("至", "-")
        match = re.fullmatch(r"\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*", normalized)
        if not match:
            return normalized, None, 0
        start, end = match.groups()
        start_minutes = int(start[:2]) * 60 + int(start[3:])
        end_minutes = int(end[:2]) * 60 + int(end[3:])
        duration = end_minutes - start_minutes
        return start, end, duration if duration > 0 else 0

    @staticmethod
    def _align_plan_cities(structured_plan, city_plan: list[dict], start_date):
        """Make the planned day-to-city allocation authoritative for raw Skill rows.

        The Skill's prose format often omits city labels.  Without this pass the
        parser assigns every row to the first destination city, which corrupts
        hotel and intercity-transport completion for multi-city trips.
        """
        if len({item.get("city") for item in city_plan if item.get("city")}) <= 1:
            return structured_plan
        city_by_day: dict[int, str] = {}
        for segment in city_plan:
            city, segment_start = segment.get("city"), segment.get("start_date")
            if not city or segment_start is None:
                continue
            first_day = max(1, (segment_start - start_date).days + 1)
            for day_number in range(first_day, first_day + int(segment.get("days", 0))):
                city_by_day[day_number] = city
        return replace(
            structured_plan,
            items=tuple(replace(item, city=city_by_day.get(item.day_number, item.city)) for item in structured_plan.items),
        )

    def _city_plan(self, candidates: list[Landmark], must_visit_ids: list[int], start_date, day_count: int) -> list[dict]:
        """Expose the deterministic pre-query skeleton in the existing dict shape."""
        return [segment.as_dict() for segment in self._trip_skeleton.build(candidates, must_visit_ids, start_date, day_count)]

    @staticmethod
    def _apply_city_skeleton(planned_days, candidates: list[Landmark], city_plan: list[dict], start_date):
        """Keep map stops on the same daily city schedule used for external queries."""
        city_by_id = {
            item.id: item.location.city_name
            for item in candidates
            if item.location and item.location.city_name
        }
        city_by_day: dict[int, str] = {}
        for segment in city_plan:
            first_day = (segment["start_date"] - start_date).days + 1
            for number in range(first_day, first_day + int(segment["days"])):
                city_by_day[number] = segment["city"]
        if not city_by_day:
            return planned_days

        stops_by_city: dict[str, list] = {}
        for day in planned_days:
            for stop in day.stops:
                city = city_by_id.get(stop.landmark_id)
                if city:
                    stops_by_city.setdefault(city, []).append(stop)
        days_by_city: dict[str, list[int]] = {}
        for number, city in city_by_day.items():
            days_by_city.setdefault(city, []).append(number)
        stops_for_day: dict[int, list] = {day.day_number: [] for day in planned_days}
        for city, stops in stops_by_city.items():
            target_days = days_by_city.get(city, [])
            for index, stop in enumerate(stops):
                if target_days:
                    stops_for_day[target_days[index % len(target_days)]].append(stop)
        return tuple(
            replace(
                day,
                stops=tuple(stops_for_day.get(day.day_number, [])),
                summary=f"{city_by_day.get(day.day_number, '当日目的地')}城市段行程；住宿与城市间移动均按该骨架安排。",
            )
            for day in planned_days
        )

    @staticmethod
    def _meituan_lodging_reference(structured_plan) -> dict:
        items = [item for item in structured_plan.items if item.category == "lodging"]
        return {
            "status": "已整理",
            "items": [{"city": item.city, "name": item.name, "price": item.amount, "note": item.note} for item in items],
        }

    @staticmethod
    def _meituan_transport_reference(structured_plan) -> dict:
        items = [item for item in structured_plan.items if item.category == "transport"]
        return {
            "status": "已整理",
            "legs": [{"label": item.name, "from": "", "to": item.city, "date": "", "mode": item.transport, "price": item.amount, "note": item.note} for item in items],
        }

    def _confirmed_lodging_coordinate(self, request: ItineraryCreateRequest, destination_city: str | None) -> tuple[float, float] | None:
        if not request.confirmed_lodgings:
            return None
        lodging = request.confirmed_lodgings[0]
        key = self._settings.amap_web_service_api_key.get_secret_value() if self._settings.amap_web_service_api_key else None
        if not key:
            return None
        try:
            value = AmapWebService(key).geocode(lodging.address or lodging.name, lodging.city or destination_city)
            if not value:
                return None
            lng, lat = (float(part) for part in value.split(",", 1))
            return lat, lng
        except Exception:
            return None

    def get_owned(self, user_id: int, itinerary_id: int) -> Itinerary:
        itinerary = self._db.scalar(
            select(Itinerary)
            .where(Itinerary.id == itinerary_id, Itinerary.user_id == user_id)
            .options(
                selectinload(Itinerary.days)
                .selectinload(ItineraryDay.stops)
                .selectinload(ItineraryStop.landmark)
                .selectinload(Landmark.ip_work),
                selectinload(Itinerary.days)
                .selectinload(ItineraryDay.stops)
                .selectinload(ItineraryStop.landmark)
                .selectinload(Landmark.location),
                selectinload(Itinerary.days)
                .selectinload(ItineraryDay.stops)
                .selectinload(ItineraryStop.landmark)
                .selectinload(Landmark.sources)
                .selectinload(LandmarkSource.source),
            )
        )
        if itinerary is None:
            raise ItineraryNotFound("Itinerary not found.")
        return itinerary

    def list_owned(self, user_id: int) -> list[Itinerary]:
        return self._db.scalars(
            select(Itinerary).where(Itinerary.user_id == user_id).order_by(Itinerary.updated_at.desc())
        ).all()

    def update_days(self, user_id: int, itinerary_id: int, title: str | None, days: list[ItineraryDayEdit]) -> Itinerary:
        itinerary = self.get_owned(user_id, itinerary_id)
        expected_days = (itinerary.end_date - itinerary.start_date).days + 1
        if days:
            allowed = set(itinerary.candidate_landmark_ids)
            self._validator.validate_days(days, allowed, expected_days)
            itinerary.days.clear()
            self._db.flush()
            for payload in sorted(days, key=lambda value: value.day_number):
                day = ItineraryDay(
                    day_number=payload.day_number,
                    itinerary_date=itinerary.start_date + timedelta(days=payload.day_number - 1),
                    summary=payload.summary.strip() if payload.summary else None,
                    supplemental_items=[],
                    travel_context={},
                )
                day.stops = [
                    ItineraryStop(
                        landmark_id=stop.landmark_id,
                        stop_order=index,
                        time_slot=stop.time_slot,
                        planned_minutes=stop.planned_minutes,
                        selection_reason=stop.selection_reason,
                        user_note=stop.user_note.strip() if stop.user_note else None,
                    )
                    for index, stop in enumerate(payload.stops, start=1)
                ]
                itinerary.days.append(day)
            itinerary.used_landmark_ids = [stop.landmark_id for day in days for stop in day.stops]
        if title:
            itinerary.title = title.strip()
        itinerary.version += 1
        self._db.commit()
        return self.get_owned(user_id, itinerary.id)

    def delete(self, user_id: int, itinerary_id: int) -> None:
        itinerary = self.get_owned(user_id, itinerary_id)
        self._db.delete(itinerary)
        self._db.commit()

    def _load_candidates(self, request: ItineraryCreateRequest) -> list[Landmark]:
        base = published_landmark_statement(CatalogFilters.from_values(request.ip_type, request.work, "CN"))
        required = self._db.scalars(
            base.where(Landmark.id.in_(request.must_visit_landmark_ids))
            .options(selectinload(Landmark.ip_work), selectinload(Landmark.location))
        ).all() if request.must_visit_landmark_ids else []
        cities = {item.location.city_name for item in required if item.location and item.location.city_name}
        statement = published_landmark_statement(CatalogFilters.from_values(request.ip_type, request.work, "CN"))
        if cities:
            statement = statement.where(Landmark.location.has(Location.city_name.in_(cities)))
        candidates = self._db.scalars(
            statement
            .where(Landmark.verification_status == VerificationStatus.VERIFIED)
            .options(selectinload(Landmark.ip_work), selectinload(Landmark.location))
            .order_by(Landmark.id)
        ).all()
        return candidates

    @staticmethod
    def _default_title(destination_city: str | None, day_count: int) -> str:
        return f"{destination_city or '国内'} IP 地标 {day_count} 日游"

    @staticmethod
    def _cluster_days_by_city(
        planned_days: tuple[PlannedDay, ...],
        candidates: list[Landmark],
        must_visit_ids: list[int],
        daily_hours: int,
    ) -> tuple[PlannedDay, ...]:
        """Give each day one city cluster so users do not bounce between cities."""
        by_id = {item.id: item for item in candidates}
        city_by_id = {
            item.id: (item.location.city_name if item.location and item.location.city_name else "未标注城市")
            for item in candidates
        }
        all_stops = [stop for day in planned_days for stop in day.stops]
        city_order: list[str] = []
        for landmark_id in must_visit_ids + [stop.landmark_id for stop in all_stops]:
            city = city_by_id.get(landmark_id)
            if city and city not in city_order:
                city_order.append(city)
        if len(city_order) <= 1:
            return planned_days

        grouped: dict[str, list] = {city: [] for city in city_order}
        required_set = set(must_visit_ids)
        for city in city_order:
            city_stops = [stop for stop in all_stops if city_by_id.get(stop.landmark_id) == city]
            grouped[city] = sorted(city_stops, key=lambda stop: (stop.landmark_id not in required_set, stop.landmark_id))

        slots: list[str] = list(city_order)
        remaining_slots = len(planned_days) - len(slots)
        while remaining_slots > 0:
            city = max(city_order, key=lambda value: len(grouped[value]) / max(1, slots.count(value)))
            slots.append(city)
            remaining_slots -= 1
        cursor = {city: 0 for city in city_order}
        result: list[PlannedDay] = []
        for template, city in zip(planned_days, slots):
            remaining_city_days = slots[slots.index(city, len(result)):].count(city)
            remaining_stops = grouped[city][cursor[city]:]
            take = (len(remaining_stops) + remaining_city_days - 1) // remaining_city_days if remaining_city_days else len(remaining_stops)
            selected = tuple(remaining_stops[:take])
            cursor[city] += take
            summary = f"{city}城市片区游览；当天景点集中安排，减少跨城往返。"
            result.append(replace(template, summary=summary, stops=selected))
        return tuple(result)

    @staticmethod
    def _distribute_supplemental_items(
        items: tuple[dict, ...], planned_days: tuple[PlannedDay, ...], candidates: list[Landmark]
    ) -> dict[int, list[dict]]:
        by_day: dict[int, list[dict]] = {day.day_number: [] for day in planned_days}
        candidate_city = {item.id: item.location.city_name if item.location else None for item in candidates}
        for index, item in enumerate(items):
            day = min(
                planned_days,
                key=lambda value: (len(by_day[value.day_number]), index % len(planned_days) != value.day_number - 1),
            )
            scheduled = dict(item)
            scheduled["scheduled_city"] = candidate_city.get(day.stops[0].landmark_id) if day.stops else None
            scheduled["route_note"] = "与当天已安排地标同区域优先，具体位置与开放情况请出行前确认。"
            by_day[day.day_number].append(scheduled)
        return by_day

    @staticmethod
    def _city_plan_from_days(planned_days: tuple[PlannedDay, ...], candidates: list[Landmark]) -> list[dict]:
        city_by_id = {item.id: item.location.city_name if item.location else None for item in candidates}
        result: list[dict] = []
        for day in planned_days:
            city = city_by_id.get(day.stops[0].landmark_id) if day.stops else None
            if result and result[-1]["city"] == city:
                result[-1]["days"] += 1
                result[-1]["nights"] += 1
                continue
            result.append({"city": city, "days": 1, "nights": 1, "start_date": day.itinerary_date})
        if result:
            result[-1]["nights"] = max(0, result[-1]["nights"] - 1)
        return [item for item in result if item["city"]]

    @staticmethod
    def _landmark_names_by_city(candidates: list[Landmark]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for landmark in candidates:
            city = landmark.location.city_name if landmark.location else None
            if city:
                result.setdefault(city, []).append(landmark.name)
        return result

    @staticmethod
    def _build_day_contexts(
        request: ItineraryCreateRequest,
        planned_days: tuple[PlannedDay, ...],
        candidates: list[Landmark],
        enrichment,
        destination_city: str | None,
        lodging_coordinate: tuple[float, float] | None,
    ) -> dict[int, dict]:
        city_by_id = {item.id: item.location.city_name if item.location else destination_city for item in candidates}
        transport_legs = (enrichment.transport_reference or {}).get("legs", [])
        lodgings_by_city = {
            item.get("city"): item for item in (enrichment.lodging_reference or {}).get("cities", [])
        }
        contexts: dict[int, dict] = {}
        for day in planned_days:
            city = city_by_id.get(day.stops[0].landmark_id, destination_city) if day.stops else destination_city
            day_transport = []
            if day.day_number == 1:
                day_transport.extend(leg for leg in transport_legs if leg.get("label") == "去程")
            if day.day_number == len(planned_days):
                day_transport.extend(leg for leg in transport_legs if leg.get("label") == "返程")
            previous_city = contexts.get(day.day_number - 1, {}).get("city")
            if previous_city and city and previous_city != city:
                day_transport.insert(0, {
                    "label": "城市间移动",
                    "from": previous_city,
                    "to": city,
                    "date": day.itinerary_date.isoformat(),
                    "note": "已将不同城市拆分到相邻日期；建议从美团候选中确认高铁、动车或机票。",
                })
            lodging_reference = lodgings_by_city.get(city, {})
            lodging = {
                "mode": request.lodging_mode,
                "city": city,
                "name": lodging_reference.get("name"),
                "address": lodging_reference.get("address"),
                "options": lodging_reference.get("options", []),
                "status": lodging_reference.get("status"),
                "is_route_anchor": lodging_coordinate is not None and (request.lodging_city in (None, city)),
                "note": "当天从住宿出发并返回住宿；已根据住宿坐标优先安排最近的首站。" if lodging_coordinate and request.lodging_city in (None, city) else "住宿按当前城市安排；未取得该城市住宿坐标时仅按景点区域优化顺序。",
            }
            contexts[day.day_number] = {"city": city, "lodging": lodging, "intercity_transport": day_transport}
        return contexts

    @staticmethod
    def _apply_days(
        itinerary: Itinerary,
        days: tuple[PlannedDay, ...],
        supplemental_by_day: dict[int, list[dict]] | None = None,
        travel_context_by_day: dict[int, dict] | None = None,
    ) -> None:
        for payload in days:
            day = ItineraryDay(
                day_number=payload.day_number,
                itinerary_date=payload.itinerary_date,
                summary=payload.summary,
                supplemental_items=(supplemental_by_day or {}).get(payload.day_number, []),
                travel_context=(travel_context_by_day or {}).get(payload.day_number, {}),
            )
            day.stops = [
                ItineraryStop(
                    landmark_id=stop.landmark_id,
                    stop_order=index,
                    time_slot=stop.time_slot,
                    planned_minutes=stop.planned_minutes,
                    selection_reason=stop.selection_reason,
                )
                for index, stop in enumerate(payload.stops, start=1)
            ]
            itinerary.days.append(day)
