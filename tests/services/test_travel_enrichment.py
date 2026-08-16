from datetime import date

from app.schemas.itinerary import ItineraryCreateRequest
from app.services.travel_enrichment import TravelEnrichmentService
from app.integrations.amap_web_service import AmapPoi


class FakeMeituan:
    def is_available(self):
        return True

    def query(self, city, query):
        class Result:
            content = (
                '[清明上河园](https://example.com/qingming)\n'
                '<ka type=hotel id=1>{"name":"鼓楼民宿"}</ka>\n'
                '<ka type=transport id=G25@BJP@SHH@2026-09-01>["二等座"]</ka>'
            )
        return Result()


def test_enrichment_adds_nearby_suggestions_lodging_and_transport_references():
    request = ItineraryCreateRequest(
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2), origin_city="郑州",
        must_visit_landmark_ids=[1], budget_amount=2000,
    )
    result = TravelEnrichmentService(FakeMeituan()).enrich(
        request,
        [{"city": "开封", "days": 2, "nights": 1, "start_date": date(2026, 9, 1)}],
        {"开封": ["开封府"]},
    )

    assert result.supplemental_items[0]["name"] == "清明上河园"
    option = result.lodging_reference["cities"][0]["options"][0]
    assert option["name"] == "鼓楼民宿"
    assert option["price"] is None
    assert option["price_info"]["level"] == "unavailable"
    assert result.transport_reference["legs"][0]["train_options"][0]["id"].startswith("G25")


def test_enrichment_queries_city_to_city_transport_and_recommends_each_city_lodging():
    request = ItineraryCreateRequest(
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 3), origin_city="郑州",
        must_visit_landmark_ids=[1], budget_amount=3000,
    )
    city_plan = [
        {"city": "开封", "days": 1, "nights": 1, "start_date": date(2026, 9, 1)},
        {"city": "洛阳", "days": 2, "nights": 1, "start_date": date(2026, 9, 2)},
    ]
    result = TravelEnrichmentService(FakeMeituan()).enrich(request, city_plan, {"开封": ["开封府"], "洛阳": ["龙门石窟"]})

    assert [item["city"] for item in result.lodging_reference["cities"]] == ["开封", "洛阳"]
    assert any(leg["label"] == "城市间移动" and leg["from"] == "开封" and leg["to"] == "洛阳" for leg in result.transport_reference["legs"])


def test_enrichment_marks_meituan_prices_as_confirmable_and_amap_cost_as_reference():
    class PricedMeituan:
        def query(self, city, query):
            class Result:
                content = '<ka type=hotel id=1>{"name":"鼓楼酒店"}</ka>\n<ka type=transport id=G25>["二等座"]</ka>\n¥188'
            return Result()

    request = ItineraryCreateRequest(
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2), origin_city="郑州", must_visit_landmark_ids=[1]
    )
    result = TravelEnrichmentService(PricedMeituan()).enrich(
        request, [{"city": "开封", "days": 2, "nights": 1, "start_date": date(2026, 9, 1)}], {"开封": ["开封府"]}
    )

    assert result.lodging_reference["cities"][0]["options"][0]["price_info"]["level"] == "confirmable"
    assert result.transport_reference["legs"][0]["train_options"][0]["price_info"]["level"] == "confirmable"


def test_enrichment_uses_amap_cost_only_as_reference_when_meituan_has_no_price():
    class FakeAmap:
        def search_poi(self, *args, **kwargs):
            return (AmapPoi("poi", "鼓楼民宿", "开封地址", None, reference_cost=260),)

    request = ItineraryCreateRequest(
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2), origin_city="郑州", must_visit_landmark_ids=[1]
    )
    result = TravelEnrichmentService(FakeMeituan(), amap=FakeAmap()).enrich(
        request, [{"city": "开封", "days": 2, "nights": 1, "start_date": date(2026, 9, 1)}], {"开封": ["开封府"]}
    )

    price_info = result.lodging_reference["cities"][0]["options"][0]["price_info"]
    assert price_info == {"amount": 260, "source": "高德地图 POI", "level": "reference", "url": None}
