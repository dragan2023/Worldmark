"""Complete prices omitted from a Meituan itinerary without inventing them."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import timedelta
import re

from app.integrations.amap_web_service import AmapServiceError, AmapWebService
from app.integrations.meituan_travel_mcp import MeituanMcpError, MeituanMcpUnavailable, MeituanTravelMcp
from app.integrations.search.bocha_web_search import BochaWebSearchProvider, SearchConfigurationError, SearchProviderError
from app.services.meituan_itinerary_parser import StructuredTravelPlan, TravelPlanItem


_MONEY = re.compile(r"(?:¥|￥|人民币|RMB)\s*(\d+(?:\.\d+)?)|(?<!\d)(\d+(?:\.\d+)?)\s*元")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_HOTEL = re.compile(r'<ka type=hotel[^>]*>\s*\{[^}]*"name"\s*:\s*"([^"]+)"')
_HOTEL_KEYWORD = re.compile(r"(?:酒店|民宿|客栈|宾馆|饭店|公寓)")


class TravelPriceCompletionService:
    """Use Meituan first; only then use map/search reference prices as a fallback."""

    meituan_source = "美团酒旅官方 Skill"
    amap_source = "高德地图 POI"
    bocha_source = "博查 AI 搜索"

    def __init__(self, adapter: MeituanTravelMcp | None, *, amap: AmapWebService | None = None, bocha_api_key: str | None = None) -> None:
        self._adapter = adapter
        self._amap = amap
        self._bocha = BochaWebSearchProvider(bocha_api_key) if bocha_api_key else None

    def complete(self, plan: StructuredTravelPlan) -> StructuredTravelPlan:
        missing = [item for item in plan.items if item.amount is None and item.category in {"scenic", "food"}]
        if not missing:
            return self.review_prices(plan)
        meituan_prices: dict[tuple[str, str], int] = {}
        for city, items in self._group_by_city(missing).items():
            meituan_prices.update(self._meituan_batch_prices(city, items))

        completed: list[TravelPlanItem] = []
        sources: dict[str, str] = {}
        for item in plan.items:
            key = (item.city, item.name)
            if item.amount is not None or item.category not in {"scenic", "food"}:
                completed.append(item)
                continue
            price = meituan_prices.get(key)
            source = self.meituan_source if price is not None else None
            if price is None:
                price = self._amap_price(item)
                source = self.amap_source if price is not None else None
            if price is None:
                price = self._bocha_price(item)
                source = self.bocha_source if price is not None else None
            if price is not None:
                completed.append(replace(item, amount=price))
                sources[self.source_key(item)] = source or "第三方参考"
            else:
                completed.append(item)

        budget = self._budget(completed)
        budget["price_sources"] = sources
        budget["status"] = "已汇总行程价格及补充参考价格，出行前请核验。"
        return self.review_prices(StructuredTravelPlan(tuple(completed), budget, plan.warning))

    def review_prices(self, plan: StructuredTravelPlan) -> StructuredTravelPlan:
        """Keep a price only when a separate Bocha web search can corroborate it.

        Search snippets often contain unrelated article counts, bundle prices, or
        hotel totals.  The final itinerary must prefer a blank amount over a
        plausible-looking but untrustworthy number.
        """
        suspicious = [
            item for item in plan.items
            if item.category in {"scenic", "food"} and item.amount is not None and not self._is_reasonable_price(item.amount, item.category)
        ]
        if not suspicious:
            return plan

        verified: dict[tuple[str, str], int] = {}
        if self._bocha is not None:
            for item in suspicious:
                if price := self._bocha_item_review(item):
                    verified[(item.city, item.name)] = price

        sources = dict(plan.budget.get("price_sources") or {})
        reviewed: list[TravelPlanItem] = []
        for item in plan.items:
            if item not in suspicious:
                reviewed.append(item)
                continue
            price = verified.get((item.city, item.name))
            if price is None:
                sources.pop(self.source_key(item), None)
                reviewed.append(replace(item, amount=None))
                continue
            sources[self.source_key(item)] = self.bocha_source
            reviewed.append(replace(item, amount=price))

        budget = self._budget(reviewed)
        budget["price_sources"] = sources
        budget["price_review_status"] = (
            "异常价格已通过博查网页独立复核；没有明确项目价格的信息已留空。"
            if self._bocha is not None
            else "未配置博查网页搜索，异常价格未展示。"
        )
        budget["status"] = "已汇总合理范围内的价格；异常价格须经独立网页搜索复核后才会计入预算。"
        return StructuredTravelPlan(tuple(reviewed), budget, plan.warning)

    def complete_transport(
        self,
        plan: StructuredTravelPlan,
        request,
        destination_city: str,
        *,
        city_plan: list[dict] | None = None,
    ) -> StructuredTravelPlan:
        """Complete every missing long-distance leg, including transfers between cities."""
        if self._adapter is None:
            return plan
        legs = self._transport_legs(request, destination_city, city_plan)
        existing = [item for item in plan.items if item.category == "transport"]
        additions: list[TravelPlanItem] = []
        for day_number, travel_date, departure, arrival, label in legs:
            if not departure or not arrival or departure == arrival:
                continue
            if self._has_transport_leg(existing, label, departure, arrival):
                continue
            query = (
                f"查询 {travel_date.isoformat()} {departure} 到 {arrival} 的火车或飞机。"
                "请直接返回一条优先推荐的可行方案，格式固定为："
                "方式｜班次或航班号｜出发时间｜到达时间｜含税参考票价。"
                "班次与票价必须来自查询结果；没有可靠价格时写“票价待确认”，不要省略班次。"
            )
            try:
                content = self._adapter.query(departure, query, origin_query=query).content
            except (MeituanMcpUnavailable, MeituanMcpError):
                content = ""
            if item := self._transport_item(content, day_number, arrival, label, departure, arrival):
                additions.append(item)
            else:
                additions.append(TravelPlanItem(day_number, destination_city, "待确认", f"{label}：{departure} → {arrival}", "火车/飞机", "班次与票价待确认", None, "transport"))
        items = list(plan.items) + additions
        budget = self._budget(items)
        budget.update({key: value for key, value in plan.budget.items() if key not in {"estimated_amount", "breakdown", "unpriced_item_count"}})
        return StructuredTravelPlan(tuple(self._sort_items(items)), budget, plan.warning)

    def complete_lodging(
        self,
        plan: StructuredTravelPlan,
        request,
        destination_city: str,
        *,
        city_plan: list[dict] | None = None,
    ) -> StructuredTravelPlan:
        """Query lodging per city segment instead of copying one hotel across a trip."""
        expected_nights = max(0, (request.end_date - request.start_date).days)
        if expected_nights == 0 or self._adapter is None:
            return plan
        segments = self._lodging_segments(request, destination_city, city_plan)
        is_multi_city = len({segment["city"] for segment in segments}) > 1
        # The main route prompt intentionally does not ask for hotels.  In a
        # multi-city trip, any legacy hotel extracted from that response has no
        # reliable city binding, so replace it with city-specific searches.
        items = [item for item in plan.items if item.category != "lodging"] if is_multi_city else list(plan.items)
        additions: list[TravelPlanItem] = []
        existing_lodging_days = {item.day_number for item in items if item.category == "lodging"}
        for segment in segments:
            city, check_in, nights, first_day = segment["city"], segment["check_in"], segment["nights"], segment["first_day"]
            if nights <= 0:
                continue
            query = (
                f"请查询{city}在{check_in.isoformat()}入住、{(check_in + timedelta(days=nights)).isoformat()}离店、"
                f"{request.traveler_count}人入住的酒店或民宿。推荐一间靠近当天主要景点的可入住选项，"
                "给出名称、区域、每晚价格；如果没有可靠价格，明确写待确认。"
            )
            try:
                content = self._adapter.query(city, query, origin_query=query).content
            except (MeituanMcpUnavailable, MeituanMcpError):
                content = ""
            name, amount = self._lodging_option(content, city)
            for offset in range(nights):
                day_number = first_day + offset
                if day_number in existing_lodging_days:
                    continue
                additions.append(
                    TravelPlanItem(
                        day_number,
                        city,
                        "20:00",
                        f"入住：{name}",
                        "打车",
                        "每晚住宿安排" if amount is not None else "住宿与价格待确认",
                        amount,
                        "lodging",
                    )
                )
        items.extend(additions)
        budget = self._budget(items)
        budget.update({key: value for key, value in plan.budget.items() if key not in {"estimated_amount", "breakdown", "unpriced_item_count"}})
        return StructuredTravelPlan(tuple(self._sort_items(items)), budget, plan.warning)

    @staticmethod
    def _group_by_city(items: list[TravelPlanItem]) -> dict[str, list[TravelPlanItem]]:
        grouped: dict[str, list[TravelPlanItem]] = defaultdict(list)
        for item in items:
            grouped[item.city].append(item)
        return grouped

    def _meituan_batch_prices(self, city: str, items: list[TravelPlanItem]) -> dict[tuple[str, str], int]:
        if self._adapter is None:
            return {}
        scenic = [item.name for item in items if item.category == "scenic"]
        food = [item.name for item in items if item.category == "food"]
        query = (
            f"请查询 {city} 以下项目的当前参考价格：景点成人门票：{'、'.join(scenic) or '无'}；"
            f"餐饮人均消费：{'、'.join(food) or '无'}。"
            "必须逐项给出，使用 Markdown 表格，列为：项目｜类别｜价格(元)。"
            "没有价格必须明确写待确认；不要给总价、不要省略任何项目。"
        )
        try:
            content = self._adapter.query(city, query, origin_query=query).content
        except (MeituanMcpUnavailable, MeituanMcpError):
            return {}
        return {(city, item.name): price for item in items if (price := self._price_near_name(content, item.name)) is not None}

    def _amap_price(self, item: TravelPlanItem) -> int | None:
        if self._amap is None:
            return None
        try:
            pois = self._amap.search_poi(item.name, item.city, page_size=1, include_details=True)
        except (AmapServiceError, ValueError):
            return None
        return pois[0].reference_cost if pois else None

    def _bocha_price(self, item: TravelPlanItem) -> int | None:
        if self._bocha is None:
            return None
        label = "成人门票价格" if item.category == "scenic" else "人均消费价格"
        try:
            result = self._bocha.search(f"{item.city} {item.name} {label}")
        except (SearchConfigurationError, SearchProviderError):
            return None
        content = "\n".join(f"{reference.title}\n{reference.snippet or ''}" for reference in result.references)
        return self._valid_price_near_name(content, item.name, item.category)

    def _bocha_item_review(self, item: TravelPlanItem) -> int | None:
        try:
            result = self._bocha.search(
                f"{item.city} {item.name} {'成人门票' if item.category == 'scenic' else '人均消费'} 价格。"
                "仅返回能明确对应项目名称和人民币价格的网页信息；套餐总价、商品价格、培训价格和无关数字不采纳。"
            )
        except (SearchConfigurationError, SearchProviderError):
            return None
        content = "\n".join(f"{reference.title}\n{reference.snippet or ''}" for reference in result.references)
        return self._valid_price_near_name(content, item.name, item.category)

    @classmethod
    def _price_near_name(cls, content: str, name: str) -> int | None:
        lines = content.splitlines()
        for index, line in enumerate(lines):
            if name in line:
                for candidate in lines[index : index + 2]:
                    if price := cls._first_price(candidate):
                        return price
        return None

    @classmethod
    def _valid_price_near_name(cls, content: str, name: str, category: str) -> int | None:
        lines = content.splitlines()
        for index, line in enumerate(lines):
            if name not in line:
                continue
            for candidate in lines[index : index + 2]:
                # In a compact search snippet several projects can share one
                # line.  Only inspect the text following this exact project
                # name, never the first currency figure in the whole snippet.
                scoped = candidate.split(name, 1)[1] if name in candidate else candidate
                if price := cls._first_valid_price(scoped, category):
                    return price
        return None

    @staticmethod
    def _first_price(value: str) -> int | None:
        match = _MONEY.search(value or "")
        return int(float(match.group(1) or match.group(2))) if match else None

    @classmethod
    def _first_valid_price(cls, value: str, category: str) -> int | None:
        price = cls._first_price(value)
        if price is None:
            return None
        return price if cls._is_reasonable_price(price, category) else None

    @staticmethod
    def _is_reasonable_price(price: int, category: str) -> bool:
        ceiling = 500 if category == "food" else 2000
        return 0 < price <= ceiling

    @classmethod
    def _transport_item(cls, content: str, day_number: int, city: str, label: str, departure: str, arrival: str) -> TravelPlanItem | None:
        if not content:
            return None
        time_match = re.search(r"(\d{1,2}:\d{2})", content)
        price = cls._first_price(content)
        number_match = re.search(r"\b(?:G|D|C|K|T|Z|MU|CA|CZ|HU|MF|3U)\d{2,5}\b", content)
        if price is None and number_match is None:
            return None
        time_slot = time_match.group(1) if time_match else "待确认"
        identifier = number_match.group(0) if number_match else "班次待确认"
        note = f"班次：{identifier}" if price is not None else f"班次：{identifier}；票价待确认"
        return TravelPlanItem(day_number, city, time_slot, f"{label}：{departure} → {arrival}", "高铁/火车" if identifier[0].isalpha() and identifier[0] in "GDCKTZ" else "飞机", note, price, "transport")

    @staticmethod
    def _transport_legs(request, destination_city: str, city_plan: list[dict] | None) -> list[tuple[int, object, str, str, str]]:
        if not city_plan:
            city_plan = [{"city": destination_city, "start_date": request.start_date, "days": (request.end_date - request.start_date).days + 1}]
        segments = [item for item in city_plan if item.get("city")]
        if not segments:
            return []
        result = [(1, request.start_date, request.origin_city, segments[0]["city"], "去程")]
        for previous, current in zip(segments, segments[1:]):
            result.append((
                TravelPriceCompletionService._day_number(request.start_date, current.get("start_date")),
                current.get("start_date") or request.start_date,
                previous["city"],
                current["city"],
                "城市间移动",
            ))
        result.append((
            (request.end_date - request.start_date).days + 1,
            request.end_date,
            segments[-1]["city"],
            request.return_city or request.origin_city,
            "返程",
        ))
        return result

    @staticmethod
    def _has_transport_leg(items: list[TravelPlanItem], label: str, departure: str, arrival: str) -> bool:
        route = f"{departure} → {arrival}"
        return any(item.name.startswith(f"{label}：") and route in item.name for item in items)

    @staticmethod
    def _day_number(start_date, value) -> int:
        if value is None:
            return 1
        return max(1, (value - start_date).days + 1)

    @staticmethod
    def _lodging_segments(request, destination_city: str, city_plan: list[dict] | None) -> list[dict]:
        if not city_plan:
            return [{"city": destination_city, "check_in": request.start_date, "nights": max(0, (request.end_date - request.start_date).days), "first_day": 1}]
        segments = []
        for item in city_plan:
            city = item.get("city")
            if not city:
                continue
            check_in = item.get("start_date") or request.start_date
            segments.append({
                "city": city,
                "check_in": check_in,
                "nights": max(0, int(item.get("nights", 0))),
                "first_day": TravelPriceCompletionService._day_number(request.start_date, check_in),
            })
        return segments

    @staticmethod
    def _sort_items(items: list[TravelPlanItem]) -> list[TravelPlanItem]:
        def key(item: TravelPlanItem) -> tuple[int, int, str]:
            match = re.match(r"(\d{1,2}):(\d{2})", item.time_slot)
            return item.day_number, int(match.group(1)) * 60 + int(match.group(2)) if match else 24 * 60, item.name
        return sorted(items, key=key)

    @classmethod
    def _lodging_option(cls, content: str, city: str) -> tuple[str, int | None]:
        hotel = _HOTEL.search(content)
        if hotel:
            return hotel.group(1).strip(), cls._first_price(content)
        for line in content.splitlines():
            link = _LINK.search(line)
            if link and any(token in link.group(1) for token in ("酒店", "民宿", "客栈", "公寓")):
                return link.group(1).replace("**", "").strip(), cls._first_price(line)
        for line in content.splitlines():
            if cls._is_hotel_name_line(line):
                return cls._clean_hotel_name(line), cls._first_price(line)
        return f"{city}住宿待确认", None

    @staticmethod
    def _is_hotel_name_line(value: str) -> bool:
        clean = value.replace("**", "").strip().lstrip("-•0123456789. ")
        return (
            bool(_HOTEL_KEYWORD.search(clean))
            and len(clean) <= 80
            and not any(token in clean for token in ("小团", "帮你", "挑选", "考虑到", "景点", "入住", "离店", "评价", "性价比", "😊"))
        )

    @staticmethod
    def _clean_hotel_name(value: str) -> str:
        clean = value.replace("**", "").strip().lstrip("-•0123456789. ")
        return re.split(r"[，。；：]|\s*(?:¥|￥|人民币|RMB)", clean, maxsplit=1)[0].strip()

    @staticmethod
    def source_key(item: TravelPlanItem) -> str:
        return f"{item.day_number}:{item.name}"

    @staticmethod
    def _budget(items: list[TravelPlanItem]) -> dict:
        breakdown = {"transport": 0, "lodging": 0, "scenic": 0, "food": 0, "other": 0}
        missing = 0
        for item in items:
            if item.amount is None:
                missing += 1
            else:
                breakdown[item.category] += item.amount
        return {"estimated_amount": sum(breakdown.values()), "breakdown": breakdown, "unpriced_item_count": missing}
