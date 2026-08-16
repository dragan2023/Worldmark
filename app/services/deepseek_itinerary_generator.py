"""DeepSeek-backed itinerary generator."""

from datetime import date, timedelta
import json

from app.integrations.deepseek_client import DeepSeekClient, DeepSeekClientError
from app.models.landmark import Landmark
from app.services.mock_itinerary_generator import PlannedDay, PlannedStop


class ItineraryGenerationError(RuntimeError):
    """Raised when the LLM generator cannot produce a valid itinerary."""


class DeepSeekItineraryGenerator:
    version = "deepseek-v2"

    _SYSTEM_PROMPT = """你是一名专业的国内 IP 主题旅行规划师。请根据用户的候选地标、交通、住宿和本地旅行资料，输出完整、可执行的行程 JSON。
输出规则：
1. 只输出 JSON 对象，不要 markdown 或解释文字。
2. 输出必须是完整闭合的 JSON，字段和层级与示例一致。
3. landmark_id 只能使用候选地标清单中的 id，不能编造。
4. 必去 landmark_id 必须全部出现。
5. 同一天优先安排相邻区域，避免折返；有住宿信息时，以住宿为日常动线锚点。
6. 交通、住宿、预算和本地旅行资料是规划依据；价格、余票和营业信息均须以出发前实际查询为准。"""

    def __init__(self, client: DeepSeekClient) -> None:
        self._client = client

    def generate(
        self,
        candidates: list[Landmark],
        must_visit_ids: list[int],
        start_date: date,
        total_days: int,
        daily_hours: int,
        planning_context: dict | None = None,
    ) -> tuple[PlannedDay, ...]:
        by_id = {item.id: item for item in candidates}
        prompt = self._build_user_prompt(
            self._describe_candidates(candidates),
            must_visit_ids,
            total_days,
            daily_hours,
            planning_context or {},
        )
        try:
            payload = self._client.generate_json(
                [{"role": "system", "content": self._SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
            )
        except DeepSeekClientError as exc:
            raise ItineraryGenerationError(str(exc)) from exc
        return self._parse_days(payload, by_id, must_visit_ids, start_date, total_days)

    @staticmethod
    def _describe_candidates(candidates: list[Landmark]) -> list[dict]:
        return [
            {
                "id": item.id,
                "name": item.name,
                "work": item.ip_work.title if item.ip_work else "",
                "city": item.location.city_name if item.location else None,
                "address": item.location.normalized_address if item.location else "",
                "summary": item.description,
                "latitude": item.location.latitude if item.location else None,
                "longitude": item.location.longitude if item.location else None,
            }
            for item in candidates
        ]

    @staticmethod
    def _build_user_prompt(
        candidate_rows: list[dict],
        must_visit_ids: list[int],
        total_days: int,
        daily_hours: int,
        planning_context: dict,
    ) -> str:
        example = {
            "days": [
                {
                    "day_number": 1,
                    "summary": "当天主题与动线说明",
                    "stops": [
                        {
                            "landmark_id": 1,
                            "time_slot": "09:00",
                            "planned_minutes": 120,
                            "selection_reason": "与 IP 的关联和纳入此日动线的理由",
                        }
                    ],
                }
            ]
        }
        return (
            f"行程天数：{total_days}；每日可安排时长：约 {daily_hours} 小时。\n"
            f"必去地标编号：{must_visit_ids or []}。\n"
            "请完整覆盖所有行程日；根据实际体验合理决定每天的地标数量和停留时长，不使用固定数量上限。\n"
            f"候选地标清单：\n{json.dumps(candidate_rows, ensure_ascii=False, default=str)}\n\n"
            f"交通、住宿、预算和本地旅行资料：\n{json.dumps(planning_context, ensure_ascii=False, default=str)}\n\n"
            f"输出结构示例：\n{json.dumps(example, ensure_ascii=False, default=str)}"
        )

    @staticmethod
    def _parse_days(
        payload: dict,
        by_id: dict[int, Landmark],
        must_visit_ids: list[int],
        start_date: date,
        total_days: int,
    ) -> tuple[PlannedDay, ...]:
        raw_days = payload.get("days")
        if not isinstance(raw_days, list) or not raw_days:
            raise ItineraryGenerationError("Generated itinerary has no days.")
        allowed = set(by_id)
        used_ids: set[int] = set()
        days: list[PlannedDay] = []
        seen_days: set[int] = set()
        for raw_day in raw_days:
            if not isinstance(raw_day, dict):
                raise ItineraryGenerationError("Generated day is malformed.")
            day_number = raw_day.get("day_number")
            if not isinstance(day_number, int) or not 1 <= day_number <= total_days or day_number in seen_days:
                raise ItineraryGenerationError("Generated day number is invalid.")
            seen_days.add(day_number)
            stops: list[PlannedStop] = []
            for raw_stop in raw_day.get("stops") or []:
                if not isinstance(raw_stop, dict):
                    raise ItineraryGenerationError("Generated stop is malformed.")
                landmark_id = raw_stop.get("landmark_id")
                if landmark_id not in allowed:
                    raise ItineraryGenerationError("Generated itinerary references an unknown landmark.")
                minutes = raw_stop.get("planned_minutes")
                planned_minutes = minutes if isinstance(minutes, int) and minutes > 0 else 90
                time_slot = raw_stop.get("time_slot") if isinstance(raw_stop.get("time_slot"), str) else "09:00"
                reason = raw_stop.get("selection_reason") if isinstance(raw_stop.get("selection_reason"), str) else "DeepSeek 推荐的 IP 地标。"
                stops.append(
                    PlannedStop(
                        landmark_id=landmark_id,
                        time_slot=time_slot[:20] or "09:00",
                        planned_minutes=planned_minutes,
                        selection_reason=reason.strip() or "DeepSeek 推荐的 IP 地标。",
                    )
                )
                used_ids.add(landmark_id)
            summary = raw_day.get("summary") if isinstance(raw_day.get("summary"), str) else "围绕已选 IP 地标的建议游览顺序。"
            days.append(
                PlannedDay(
                    day_number=day_number,
                    itinerary_date=start_date + timedelta(days=day_number - 1),
                    summary=summary.strip() or "围绕已选 IP 地标的建议游览顺序。",
                    stops=tuple(stops),
                )
            )
        if len(days) != total_days:
            raise ItineraryGenerationError("Generated itinerary is missing travel days.")
        if set(must_visit_ids) - used_ids:
            raise ItineraryGenerationError("Generated itinerary omitted a required landmark.")
        return tuple(sorted(days, key=lambda day: day.day_number))
