"""External travel research and price-source reconciliation for itinerary choices."""

from dataclasses import dataclass
from datetime import UTC, datetime
import re

from app.integrations.amap_web_service import AmapServiceError, AmapWebService
from app.integrations.meituan_travel_mcp import MeituanMcpError, MeituanMcpUnavailable, MeituanTravelMcp
from app.integrations.search.bocha_web_search import BochaWebSearchProvider, SearchConfigurationError, SearchProviderError
from app.services.meituan_itinerary_parser import MeituanItineraryParser


_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_HOTEL = re.compile(r'<ka type=hotel[^>]*>\{"name":"([^"]+)"')
_TRANSPORT = re.compile(r'<ka type=transport id=([^ >]+)>\["([^"]+)"\]</ka>')
_MONEY = re.compile(r"(?:\u00a5|\uffe5)\s*(\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class TravelEnrichment:
    supplemental_items: tuple[dict, ...]
    lodging_reference: dict | None
    transport_reference: dict | None
    budget_summary: dict
    planning_context: dict


@dataclass(frozen=True)
class MeituanTravelPlan:
    """One official, complete travel-planning response for the confirmation UI."""

    status: str
    content: str | None
    source: str
    queried_at: datetime | None
    warning: str | None = None


class TravelEnrichmentService:
    meituan_source = "美团酒旅 MCP"
    amap_source = "高德地图 POI"
    bocha_source = "博查 AI 搜索"

    def __init__(
        self,
        adapter: MeituanTravelMcp | None,
        bocha_api_key: str | None = None,
        amap: AmapWebService | None = None,
    ) -> None:
        self._adapter = adapter
        self._bocha = BochaWebSearchProvider(bocha_api_key) if bocha_api_key else None
        self._amap = amap

    def plan(
        self,
        request,
        city_plan: list[dict],
        landmark_names_by_city: dict[str, list[str]],
    ) -> MeituanTravelPlan:
        """Ask the official Skill for one complete plan instead of assembling one from probes.

        The current official raw-JSON response contains its rendered recommendation
        in a ``data`` string, not a stable inventory schema.  Treat that result as
        user-visible source material.  Only explicitly confirmed selections become
        structured itinerary records later in the flow.
        """
        cities = [item.get("city") for item in city_plan if item.get("city")]
        if not cities:
            return MeituanTravelPlan("unavailable", None, self.meituan_source, None, "缺少可用于规划的目的城市。")
        if self._adapter is None:
            return MeituanTravelPlan("unavailable", None, self.meituan_source, None, "美团酒旅官方 Skill 未配置。")
        query = self._build_plan_query(request, city_plan, landmark_names_by_city)
        try:
            result = self._adapter.query(cities[0], query, origin_query=query)
        except MeituanMcpUnavailable as exc:
            return MeituanTravelPlan("unavailable", None, self.meituan_source, None, str(exc))
        except MeituanMcpError as exc:
            return MeituanTravelPlan("failed", None, self.meituan_source, None, str(exc))
        if self._has_daily_items(result.content, request, cities[0]):
            return MeituanTravelPlan("available", result.content, result.source, result.queried_at)
        retry_query = self._build_repair_query(request, city_plan, landmark_names_by_city)
        try:
            retry = self._adapter.query(cities[0], retry_query, origin_query=retry_query)
        except MeituanMcpUnavailable as exc:
            return MeituanTravelPlan("unavailable", None, self.meituan_source, None, str(exc))
        except MeituanMcpError as exc:
            return MeituanTravelPlan("failed", None, self.meituan_source, None, str(exc))
        if self._has_daily_items(retry.content, request, cities[0]):
            return MeituanTravelPlan("available", retry.content, retry.source, retry.queried_at)
        return MeituanTravelPlan("failed", None, self.meituan_source, None, "暂未获得可用的分日行程信息，请稍后重试。")

    @staticmethod
    def _build_plan_query(request, city_plan: list[dict], landmark_names_by_city: dict[str, list[str]]) -> str:
        city_schedule = "；".join(
            f"{item['city']} {item['start_date'].isoformat()}起 {item['days']}天"
            for item in city_plan
            if item.get("city")
        )
        required_landmarks = "；".join(
            f"{city}：{'、'.join(names)}" for city, names in landmark_names_by_city.items() if names
        )
        preferences = "、".join(request.interests) or "无特殊主题偏好"
        budget = f"总预算约 {request.budget_amount} 元" if request.budget_amount else "预算待用户确认"
        notes = request.free_text.strip() if request.free_text else "无"
        return (
            f"我计划从{request.origin_city}出发，{request.start_date.isoformat()}到{request.end_date.isoformat()}去{city_schedule}旅行，"
            f"最后回到{request.return_city or request.origin_city}。{request.traveler_count}人出行，"
            f"偏好{request.transport_preference}和{preferences}，{budget}。"
            f"必去：{required_landmarks or '无'}。补充要求：{notes}。\n"
            "请直接给出逐日游玩路线和餐饮安排，不要反问我。每个景点、夜游和餐饮独立成行；"
            "必去地标必须安排进对应日期。每行的城市必须严格使用上述城市顺序和日期段，"
            "跨城当天仍要标明抵达后的游玩城市。交通和住宿会由系统另行核验，不要为了补全而编造班次或酒店。\n"
            "请只输出 Markdown 表格，表头固定为："
            "| 日期 | 城市 | 时间 | 游玩地点/项目 | 交通 | 重点内容 | 费用估算(元) |。"
            "每行都写完整日期（YYYY-MM-DD）；"
            "不要输出图片、天气、优惠券、营销文案或表格外内容。"
        )

    @staticmethod
    def _build_repair_query(request, city_plan: list[dict], landmark_names_by_city: dict[str, list[str]]) -> str:
        city = next(item["city"] for item in city_plan if item.get("city"))
        landmarks = "、".join(landmark_names_by_city.get(city, [])) or "已选必去地标"
        return (
            f"请重新生成{request.start_date.isoformat()}到{request.end_date.isoformat()}的{request.origin_city}—{city}—"
            f"{request.return_city or request.origin_city}行程。上次结果不完整。"
            f"必须覆盖{landmarks}和每天活动、餐饮。"
            "只输出 Markdown 表格：| 日期 | 城市 | 时间 | 游玩地点/项目 | 交通 | 重点内容 | 费用估算(元) |。"
            "不要解释、不要提问、不要输出表格外内容。"
        )

    @staticmethod
    def _has_daily_items(content: str | None, request, destination_city: str) -> bool:
        if not content:
            return False
        parsed = MeituanItineraryParser().parse(
            content,
            start_date=request.start_date,
            day_count=(request.end_date - request.start_date).days + 1,
            default_city=destination_city,
        )
        return any(item.category in {"scenic", "food"} for item in parsed.items)

    def enrich(self, request, city_plan: list[dict], landmark_names_by_city: dict[str, list[str]]) -> TravelEnrichment:
        cities = [item["city"] for item in city_plan if item.get("city")]
        budget = {"budget_amount": request.budget_amount, "estimated_amount": None, "status": "等待可确认价格", "breakdown": {}}
        if not cities:
            return TravelEnrichment((), None, None, budget, {})

        supplemental: list[dict] = []
        bocha_references: dict[str, list[dict]] = {}
        for item in city_plan:
            city, names = item["city"], landmark_names_by_city.get(item["city"], [])
            supplemental.extend(self._nearby_items(request, city, item["days"], names))
            supplemental.extend(self._food_items(request, city, item["days"]))
            references = self._local_references(city, request.interests, names)
            bocha_references[city] = references
            supplemental.extend(self._references_as_supplements(city, references, names))

        lodging = self._lodgings(request, city_plan)
        transport = self._transport(request, city_plan)
        self._complete_budget(budget, lodging, transport, request.traveler_count)
        return TravelEnrichment(
            tuple(supplemental),
            lodging,
            transport,
            budget,
            {
                "user_preferences": {
                    "budget_amount": request.budget_amount,
                    "traveler_count": request.traveler_count,
                    "transport_preference": request.transport_preference,
                    "interests": request.interests,
                    "free_text": request.free_text,
                },
                "city_plan": city_plan,
                "lodging": lodging,
                "intercity_transport": transport,
                "bocha_destination_references": bocha_references,
                "budget": budget,
            },
        )

    def ticket_estimates(self, landmarks: list[tuple[int, str, str]]) -> dict[int, dict]:
        estimates: dict[int, dict] = {}
        for landmark_id, name, city in landmarks:
            meituan_prices = self._money_values(self._query(city, f"{city}{name}门票价格，列出成人票价格"))
            if meituan_prices:
                estimates[landmark_id] = self._price(meituan_prices[0], self.meituan_source, "reference")
                continue
            poi = self._amap_poi(name, city)
            if poi and poi.reference_cost:
                estimates[landmark_id] = self._price(poi.reference_cost, self.amap_source, "reference")
                continue
            estimate = self._bocha_price(city, f"{city}{name} 门票价格 官方")
            estimates[landmark_id] = estimate or self._price(None, None, "unavailable")
        return estimates

    def _nearby_items(self, request, city: str, day_count: int, landmark_names: list[str]) -> list[dict]:
        if not request.auto_fill_nearby:
            return []
        interests = "、".join(request.interests) or "历史文化、热门景区、夜游"
        content = self._query(city, f"{city}{'、'.join(landmark_names)}附近适合{day_count}日游的{interests}景点，优先同区域并避免重复动线")
        names = self._candidate_names(content, landmark_names, kind="scenic")
        items: list[dict] = []
        prices = self._money_values(content)
        for index, (name, url) in enumerate(names):
            poi = self._amap_poi(name, city)
            price_info = self._price(prices[index], self.meituan_source, "reference") if index < len(prices) else None
            if price_info is None and poi and poi.reference_cost:
                price_info = self._price(poi.reference_cost, self.amap_source, "reference")
            if price_info is None:
                price_info = self._bocha_price(city, f"{city}{name} 门票价格 官方") or self._price(None, None, "unavailable")
            items.append({
                "type": "系统补充景点", "name": name, "city": city, "address": poi.address if poi else None,
                "source_url": url, "source": self.meituan_source if content else (price_info.get("source") or None),
                "price": price_info["amount"] or 0, "price_info": price_info,
                "note": "作为行程规划参考；营业、预约和票价请在出发前确认。",
            })
        return items

    def _food_items(self, request, city: str, day_count: int) -> list[dict]:
        if not request.auto_fill_nearby:
            return []
        content = self._query(city, f"{city}本地特色餐饮小吃，适合{day_count}日游用餐，优先具体店铺或菜品，并列出人均价格")
        items: list[dict] = []
        prices = self._money_values(content)
        for index, (name, url) in enumerate(self._candidate_names(content, [], kind="food")):
            poi = self._amap_poi(name, city)
            price_info = self._price(prices[index], self.meituan_source, "reference") if index < len(prices) else None
            if price_info is None and poi and poi.reference_cost:
                price_info = self._price(poi.reference_cost, self.amap_source, "reference")
            if price_info is None:
                price_info = self._bocha_price(city, f"{city}{name} 人均消费 价格") or self._price(None, None, "unavailable")
            items.append({
                "type": "候选餐饮", "name": name, "city": city, "address": poi.address if poi else None,
                "source_url": url, "source": self.meituan_source if content else (price_info.get("source") or None),
                "price": price_info["amount"] or 0, "price_info": price_info,
                "note": "作为餐饮候选，系统将在行程中安排用餐时段。",
            })
        return items

    def _lodgings(self, request, city_plan: list[dict]) -> dict | None:
        if request.lodging_mode == "none":
            return None
        booked_by_city = {item.city: item for item in request.lodgings}
        if request.lodging_name or request.lodging_address:
            city = request.lodging_city or city_plan[0]["city"]
            booked_by_city.setdefault(city, type("LegacyLodging", (), {"name": request.lodging_name, "address": request.lodging_address})())
        total_nights = sum(row["nights"] for row in city_plan)
        rows: list[dict] = []
        for item in city_plan:
            city, nights = item["city"], item["nights"]
            booked = booked_by_city.get(city)
            if booked:
                rows.append({"city": city, "nights": nights, "status": "用户已订", "name": booked.name, "address": booked.address, "is_route_anchor": bool(booked.address)})
                continue
            nightly_budget = max(100, (request.budget_amount or 1200) // max(1, total_nights) // 3)
            query = f"{city}市中心或主要景点附近酒店民宿，{request.traveler_count}人入住，{item['start_date']}入住，住{nights}晚，列出酒店名称、房型、每晚实时价格和可订状态，预算{nightly_budget}元"
            content = self._query(city, query)
            names = _HOTEL.findall(content) or [name for name, _ in _LINK.findall(content) if "酒店" in name or "民宿" in name]
            prices = self._money_values(content)
            options = []
            for index, name in enumerate(names):
                price_info = self._price(prices[index], self.meituan_source, "confirmable") if index < len(prices) else None
                poi = self._amap_poi(name, city)
                if price_info is None and poi and poi.reference_cost:
                    price_info = self._price(poi.reference_cost, self.amap_source, "reference")
                if price_info is None:
                    price_info = self._bocha_price(city, f"{city}{name} {item['start_date']} 酒店 价格") or self._price(None, None, "unavailable")
                options.append({
                    "name": name, "address": poi.address if poi else None, "price": price_info["amount"],
                    "price_info": price_info, "rating": poi.rating if poi else None,
                })
            rows.append({
                "city": city, "nights": nights, "status": "系统推荐" if content else "待查询", "options": options,
                "reference_price_per_night": next((option["price"] for option in options if option["price"]), None),
                "source": self.meituan_source if content else None,
            })
        return {"status": "按城市安排", "cities": rows}

    def _transport(self, request, city_plan: list[dict]) -> dict:
        cities = [item["city"] for item in city_plan]
        legs: list[dict] = []
        legs.extend(self._query_leg("去程", request.origin_city, cities[0], request.start_date))
        for index in range(len(cities) - 1):
            legs.extend(self._query_leg("城市间移动", cities[index], cities[index + 1], city_plan[index + 1]["start_date"]))
        legs.extend(self._query_leg("返程", cities[-1], request.return_city or request.origin_city, request.end_date))
        return {"status": "查询完成" if legs else "无需跨城大交通", "legs": legs}

    def _query_leg(self, label: str, departure: str, arrival: str, travel_date) -> list[dict]:
        if departure == arrival:
            return []
        date_text = travel_date.isoformat()
        flight = self._query(departure, f"{date_text} {departure}到{arrival}的机票，列出航班、舱位、含税实时价格和可订状态")
        train = self._query(departure, f"{date_text} {departure}到{arrival}的火车票，列出车次、座席、实时票价和可订状态")
        return [{
            "label": label, "from": departure, "to": arrival, "date": date_text,
            "flight_options": self._transport_options(flight), "train_options": self._transport_options(train),
            "source": self.meituan_source,
            "note": "只有美团返回明确价格的班次可直接确认；其他价格仅作参考，需使用自定义方案确认。",
        }]

    def _transport_options(self, content: str) -> list[dict]:
        prices = self._money_values(content)
        result = []
        for index, (identifier, seat) in enumerate(_TRANSPORT.findall(content)):
            price_info = self._price(prices[index], self.meituan_source, "confirmable") if index < len(prices) else self._price(None, None, "unavailable")
            result.append({"id": identifier, "seat": seat, "price": price_info["amount"], "price_info": price_info})
        return result

    def _local_references(self, city: str, interests: list[str], landmark_names: list[str]) -> list[dict]:
        if self._bocha is None:
            return []
        try:
            result = self._bocha.search(f"{city} {' '.join(landmark_names)} {' '.join(interests)} 旅游景点 开放预约 官方")
        except (SearchConfigurationError, SearchProviderError):
            return []
        return [{"title": item.title, "url": item.url, "snippet": item.snippet, "source": self.bocha_source} for item in result.references if item.url or item.snippet]

    def _bocha_price(self, city: str, query: str) -> dict | None:
        if self._bocha is None:
            return None
        try:
            result = self._bocha.search(query)
        except (SearchConfigurationError, SearchProviderError):
            return None
        for reference in result.references:
            values = self._money_values(f"{reference.title}\n{reference.snippet or ''}")
            if values:
                return self._price(values[0], self.bocha_source, "reference", url=reference.url)
        return None

    def _amap_poi(self, name: str, city: str):
        if self._amap is None:
            return None
        try:
            pois = self._amap.search_poi(name, city, page_size=1, include_details=True)
        except (AmapServiceError, ValueError):
            return None
        return pois[0] if pois else None

    def _query(self, city: str, query: str) -> str:
        try:
            return self._adapter.query(city, query).content if self._adapter is not None else ""
        except (MeituanMcpUnavailable, MeituanMcpError):
            return ""

    @staticmethod
    def _price(amount: int | None, source: str | None, level: str, url: str | None = None) -> dict:
        return {"amount": amount, "source": source, "level": level, "url": url}

    @staticmethod
    def _money_values(content: str) -> list[int]:
        return [int(float(value)) for value in _MONEY.findall(content)]

    @staticmethod
    def _candidate_names(content: str, landmark_names: list[str], *, kind: str) -> list[tuple[str, str]]:
        result, seen = [], set()
        for name, url in _LINK.findall(content):
            clean_name = name.strip()
            valid = TravelEnrichmentService._is_food_name(clean_name) if kind == "food" else TravelEnrichmentService._is_place_name(clean_name, landmark_names, "")
            if clean_name and valid and clean_name not in seen:
                seen.add(clean_name)
                result.append((clean_name, url))
        return result

    @staticmethod
    def _references_as_supplements(city: str, references: list[dict], landmark_names: list[str]) -> list[dict]:
        return [{"type": "本地旅行参考", "name": ref["title"], "city": city, "source_url": ref["url"], "source": ref["source"], "price": 0, "price_info": TravelEnrichmentService._price(None, None, "unavailable"), "note": ref.get("snippet") or "出行前请核验开放、预约和票价信息。"} for ref in references if TravelEnrichmentService._is_place_name(ref["title"], landmark_names, city)]

    @staticmethod
    def _is_place_name(name: str, landmark_names: list[str], city: str) -> bool:
        rejected = ("攻略", "旅游", "活动", "酒店", "民宿", "图片", "优惠", "券包", "去哪", "带娃", "发布", "路线", "新闻")
        if not name or name in landmark_names or (city and city in name and len(name) > 18):
            return False
        return not any(token in name for token in rejected)

    @staticmethod
    def _is_food_name(name: str) -> bool:
        rejected = ("攻略", "旅游", "酒店", "民宿", "图片", "优惠", "券包", "活动", "新闻")
        return len(name) <= 30 and not any(token in name for token in rejected)

    @staticmethod
    def _complete_budget(budget: dict, lodging: dict | None, transport: dict, traveler_count: int) -> None:
        lodging_total = sum((item.get("reference_price_per_night") or 0) * item.get("nights", 0) for item in (lodging or {}).get("cities", []))
        transport_total = sum(
            min((option["price"] for option in leg.get("train_options", []) + leg.get("flight_options", []) if option.get("price")), default=0) * traveler_count
            for leg in transport.get("legs", [])
        )
        total = lodging_total + transport_total
        budget["breakdown"] = {"lodging": lodging_total or None, "intercity_transport": transport_total or None}
        if total:
            budget["estimated_amount"] = total
            budget["status"] = "仅汇总带明确金额的查询结果；参考价需在确认前复核。"
