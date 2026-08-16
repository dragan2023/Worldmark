from datetime import UTC, date, datetime

from app.integrations.meituan_travel_mcp import MeituanTravelResult
from app.schemas.itinerary import ItineraryCreateRequest
from app.services.travel_enrichment import TravelEnrichmentService


def _request() -> ItineraryCreateRequest:
    return ItineraryCreateRequest(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 2),
        origin_city="郑州",
        traveler_count=2,
        budget_amount=2000,
        interests=["历史文化", "美食体验"],
        must_visit_landmark_ids=[1],
        free_text="第一天上午抵达，安排轻松一些",
    )


def test_official_plan_is_a_single_complete_query_with_ip_constraints():
    class FakeMeituan:
        def __init__(self):
            self.calls = []

        def query(self, city, query, *, origin_query):
            self.calls.append((city, query, origin_query))
            return MeituanTravelResult(
                """| 日期 | 城市 | 时间 | 游玩地点/项目 | 交通 | 重点内容 | 费用估算(元) |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-01 | 开封 | 08:00 | 去程：郑州→开封 | 高铁 | 班次 | 120元 |
| 2026-09-01 | 开封 | 10:00 | 开封府 | 打车 | 游览 | 65元 |
| 2026-09-01 | 开封 | 20:00 | 入住：开封酒店 | 打车 | 一晚 | 200元 |
| 2026-09-02 | 开封 | 18:00 | 返程：开封→郑州 | 高铁 | 班次 | 120元 |""",
                {"status": "success", "data": "官方完整建议"},
                queried_at=datetime(2026, 9, 1, tzinfo=UTC),
            )

    adapter = FakeMeituan()
    plan = TravelEnrichmentService(adapter).plan(
        _request(),
        [{"city": "开封", "days": 2, "nights": 1, "start_date": date(2026, 9, 1)}],
        {"开封": ["开封府"]},
    )

    assert plan.status == "available"
    assert "去程：郑州→开封" in plan.content
    assert len(adapter.calls) == 1
    city, query, origin_query = adapter.calls[0]
    assert city == "开封"
    assert query == origin_query
    assert "开封府" in query
    assert "郑州" in query
    assert "2000" in query
    assert "逐日游玩路线和餐饮安排" in query
    assert "交通和住宿会由系统另行核验" in query
    assert "图片、天气、优惠券、营销文案或表格外内容" in query


def test_incomplete_plan_is_retried_once_with_a_targeted_repair_request():
    class FakeMeituan:
        def __init__(self):
            self.calls = []

        def query(self, city, query, *, origin_query):
            self.calls.append(query)
            content = "先告诉我预算" if len(self.calls) == 1 else """| 日期 | 城市 | 时间 | 游玩地点/项目 | 交通 | 重点内容 | 费用估算(元) |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-01 | 开封 | 08:00 | 去程：郑州→开封 | 高铁 | 班次 | 待确认 |
| 2026-09-01 | 开封 | 10:00 | 开封府 | 打车 | 游览 | 65元 |
| 2026-09-01 | 开封 | 20:00 | 入住：开封酒店 | 打车 | 一晚 | 200元 |
| 2026-09-02 | 开封 | 18:00 | 返程：开封→郑州 | 高铁 | 班次 | 待确认 |"""
            return MeituanTravelResult(content, {}, queried_at=datetime(2026, 9, 1, tzinfo=UTC))

    adapter = FakeMeituan()
    plan = TravelEnrichmentService(adapter).plan(
        _request(), [{"city": "开封", "days": 2, "nights": 1, "start_date": date(2026, 9, 1)}], {"开封": ["开封府"]}
    )

    assert plan.status == "available"
    assert len(adapter.calls) == 2
    assert "上次结果不完整" in adapter.calls[1]


def test_official_plan_failure_is_explicit_and_never_retries_with_probes():
    class UnavailableMeituan:
        def query(self, *args, **kwargs):
            from app.integrations.meituan_travel_mcp import MeituanMcpUnavailable
            raise MeituanMcpUnavailable("Token unavailable")

    plan = TravelEnrichmentService(UnavailableMeituan()).plan(
        _request(),
        [{"city": "开封", "days": 2, "nights": 1, "start_date": date(2026, 9, 1)}],
        {"开封": ["开封府"]},
    )

    assert plan.status == "unavailable"
    assert plan.content is None
    assert "Token" in plan.warning
