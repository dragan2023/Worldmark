from app.integrations.amap_web_service import AmapPoi
from app.integrations.search.base import SearchReference, SearchResult
from app.services.meituan_itinerary_parser import StructuredTravelPlan, TravelPlanItem
from app.services.travel_price_completion import TravelPriceCompletionService


def _item(name: str, category: str) -> TravelPlanItem:
    return TravelPlanItem(1, "开封市", "09:00", name, "步行/打车", "美团行程", None, category)


class _Bocha:
    def __init__(self, text: str):
        self._text = text

    def search(self, query):
        return SearchResult("test", (SearchReference("价格复核", "https://example.test", self._text),))


def test_completion_prefers_the_meituan_price_before_map_or_search():
    class Meituan:
        def query(self, city, query, *, origin_query):
            class Result:
                content = "| 项目 | 类别 | 价格(元) |\n| 开封府 | 景点 | ¥65 |\n| 灌汤包 | 餐饮 | ¥30 |"
            return Result()

    plan = StructuredTravelPlan((_item("开封府", "scenic"), _item("灌汤包", "food")), {}, None)
    service = TravelPriceCompletionService(Meituan())
    service._bocha = _Bocha("开封府 成人门票 ¥65；灌汤包 人均 ¥30")
    result = service.complete(plan)

    assert [item.amount for item in result.items] == [65, 30]
    assert result.budget["breakdown"] == {"transport": 0, "lodging": 0, "scenic": 65, "food": 30, "other": 0}
    assert result.budget["price_sources"] == {"1:开封府": "美团酒旅官方 Skill", "1:灌汤包": "美团酒旅官方 Skill"}


def test_completion_uses_amap_only_after_the_meituan_price_is_missing():
    class NoPriceMeituan:
        def query(self, city, query, *, origin_query):
            class Result:
                content = "| 项目 | 类别 | 价格(元) |\n| 开封府 | 景点 | 待确认 |"
            return Result()

    class Amap:
        def search_poi(self, *args, **kwargs):
            return (AmapPoi("poi", "开封府", "开封", None, reference_cost=60),)

    service = TravelPriceCompletionService(NoPriceMeituan(), amap=Amap())
    service._bocha = _Bocha("开封府 成人门票 ¥60")
    result = service.complete(StructuredTravelPlan((_item("开封府", "scenic"),), {}, None))

    assert result.items[0].amount == 60
    assert result.budget["price_sources"] == {"1:开封府": "高德地图 POI"}


def test_completion_adds_outbound_and_return_transport_when_the_main_plan_omits_it():
    class Meituan:
        def query(self, city, query, *, origin_query):
            class Result:
                content = "推荐 G123，08:00 出发，票价 ¥120"
            return Result()

    request = type("Request", (), {"start_date": __import__("datetime").date(2026, 9, 1), "end_date": __import__("datetime").date(2026, 9, 2), "origin_city": "郑州", "return_city": "郑州"})()
    plan = StructuredTravelPlan((_item("开封府", "scenic"),), {}, None)

    result = TravelPriceCompletionService(Meituan()).complete_transport(plan, request, "开封市")

    transport = [item for item in result.items if item.category == "transport"]
    assert [(item.day_number, item.name, item.amount) for item in transport] == [(1, "去程：郑州 → 开封市", 120), (2, "返程：开封市 → 郑州", 120)]


def test_completion_adds_each_night_of_lodging_from_an_independent_query():
    class Meituan:
        def query(self, city, query, *, origin_query):
            class Result:
                content = "[鼓楼民宿](https://example.test/hotel) ¥188起"
            return Result()

    request = type("Request", (), {"start_date": __import__("datetime").date(2026, 9, 1), "end_date": __import__("datetime").date(2026, 9, 3), "traveler_count": 2})()
    result = TravelPriceCompletionService(Meituan()).complete_lodging(StructuredTravelPlan((_item("开封府", "scenic"),), {}, None), request, "开封市")

    lodging = [item for item in result.items if item.category == "lodging"]
    assert [(item.day_number, item.name, item.amount) for item in lodging] == [(1, "入住：鼓楼民宿", 188), (2, "入住：鼓楼民宿", 188)]


def test_completion_adds_every_intercity_leg_and_keeps_a_train_when_price_is_missing():
    class Meituan:
        def query(self, city, query, *, origin_query):
            class Result:
                content = "推荐 G123，08:00 出发，票价待确认"
            return Result()

    request = type("Request", (), {"start_date": __import__("datetime").date(2026, 9, 1), "end_date": __import__("datetime").date(2026, 9, 4), "origin_city": "郑州", "return_city": "郑州"})()
    plan = StructuredTravelPlan((_item("开封府", "scenic"),), {}, None)
    city_plan = [
        {"city": "开封市", "start_date": request.start_date, "days": 2, "nights": 2},
        {"city": "洛阳市", "start_date": __import__("datetime").date(2026, 9, 3), "days": 2, "nights": 1},
    ]

    result = TravelPriceCompletionService(Meituan()).complete_transport(plan, request, "开封市", city_plan=city_plan)

    transport = [item for item in result.items if item.category == "transport"]
    assert [(item.day_number, item.city, item.name, item.amount) for item in transport] == [
        (1, "开封市", "去程：郑州 → 开封市", None),
        (3, "洛阳市", "城市间移动：开封市 → 洛阳市", None),
        (4, "郑州", "返程：洛阳市 → 郑州", None),
    ]
    assert all("票价待确认" in item.note for item in transport)


def test_completion_queries_lodging_per_city_segment_even_if_the_raw_plan_had_a_hotel():
    class Meituan:
        def query(self, city, query, *, origin_query):
            class Result:
                content = f"[{city}中心酒店](https://example.test/hotel) ¥188起"
            return Result()

    request = type("Request", (), {"start_date": __import__("datetime").date(2026, 9, 1), "end_date": __import__("datetime").date(2026, 9, 4), "traveler_count": 2})()
    raw_hotel = TravelPlanItem(1, "开封市", "20:00", "入住：旧酒店", "打车", "旧数据", 99, "lodging")
    city_plan = [
        {"city": "开封市", "start_date": request.start_date, "days": 2, "nights": 2},
        {"city": "洛阳市", "start_date": __import__("datetime").date(2026, 9, 3), "days": 2, "nights": 1},
    ]

    result = TravelPriceCompletionService(Meituan()).complete_lodging(
        StructuredTravelPlan((_item("开封府", "scenic"), raw_hotel), {}, None), request, "开封市", city_plan=city_plan
    )

    lodging = [item for item in result.items if item.category == "lodging"]
    assert [(item.day_number, item.city, item.name, item.amount) for item in lodging] == [
        (1, "开封市", "入住：开封市中心酒店", 188),
        (2, "开封市", "入住：开封市中心酒店", 188),
        (3, "洛阳市", "入住：洛阳市中心酒店", 188),
    ]


def test_price_review_removes_an_unreasonable_or_unverified_search_number():
    plan = StructuredTravelPlan(
        (TravelPlanItem(1, "朔州市", "12:00", "宋辽糖干炉", "步行", "餐饮", 96585, "food"),),
        {"price_sources": {"1:宋辽糖干炉": "博查 AI 搜索"}},
        None,
    )
    service = TravelPriceCompletionService(None)
    service._bocha = _Bocha("宋辽糖干炉 价格 ¥96585")

    result = service.review_prices(plan)

    assert result.items[0].amount is None
    assert result.budget["unpriced_item_count"] == 1


def test_price_completion_does_not_use_an_unrelated_bocha_price():
    service = TravelPriceCompletionService(None)
    service._bocha = _Bocha("山西省居民人均消费支出 ¥44649")

    result = service.complete(StructuredTravelPlan((_item("宋辽糖干炉", "food"),), {}, None))

    assert result.items[0].amount is None


def test_lodging_parser_never_uses_a_xiaotuan_narrative_as_a_hotel_name():
    name, amount = TravelPriceCompletionService._lodging_option(
        "好呀，小团帮你找到了8月16日入住忻州市的酒店。考虑到你没有指定具体景点，小团为你挑选了几家酒店。😊",
        "忻州市",
    )

    assert (name, amount) == ("忻州市住宿待确认", None)
