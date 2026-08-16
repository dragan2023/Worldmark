from datetime import date

from app.services.meituan_itinerary_parser import MeituanItineraryParser


def test_parser_normalizes_official_markdown_table_and_totals_explicit_costs():
    content = """
| 日期 | 城市 | 时间 | 游玩地点/项目 | 交通 | 重点内容 | 费用估算(元) |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-13 | 广州 | 09:00-11:00 | 广州南→市区 | 高铁/地铁 | 抵达后前往酒店 | 180元 |
|  | 广州 | 12:00-14:00 | 午餐：点都德 | 步行 | 粤式点心 | ¥120 |
|  | 广州 | 晚间 | 珠江夜游 | 地铁 | 夜游 | 待确认 |
| 2026-09-14 | 佛山 | 09:00-12:00 | 佛山祖庙门票 | 城际地铁 | 醒狮表演 | 20元 |
|  | 佛山 | 20:00 | 入住酒店 | 打车 | 两人一晚 | 360元 |
"""

    plan = MeituanItineraryParser().parse(content, start_date=date(2026, 9, 13), day_count=2, default_city="广州")

    assert [item.day_number for item in plan.items] == [1, 1, 1, 2, 2]
    assert plan.items[0].transport == "高铁/地铁"
    assert plan.items[2].amount is None
    assert plan.budget["estimated_amount"] == 680
    assert plan.budget["breakdown"] == {"transport": 180, "lodging": 360, "scenic": 20, "food": 120, "other": 0}
    assert plan.budget["unpriced_item_count"] == 1


def test_parser_preserves_explicit_outbound_and_return_rows_from_the_required_table_contract():
    content = """
| 日期 | 城市 | 时间 | 游玩地点/项目 | 交通 | 重点内容 | 费用估算(元) |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-13 | 开封 | 08:00 | 去程：郑州→开封 | 高铁 G123 | 08:00 出发，09:10 抵达 | 120元 |
| 2026-09-13 | 开封 | 10:00 | 开封府 | 打车 | 游览 | 65元 |
| 2026-09-14 | 开封 | 18:00 | 返程：开封→郑州 | 高铁 G456 | 班次待确认 | 待确认 |
"""

    plan = MeituanItineraryParser().parse(content, start_date=date(2026, 9, 13), day_count=2, default_city="开封")

    assert [(item.category, item.name, item.amount) for item in plan.items] == [
        ("transport", "去程：郑州→开封", 120),
        ("scenic", "开封府", 65),
        ("transport", "返程：开封→郑州", None),
    ]


def test_parser_returns_clear_warning_for_non_itinerary_reply():
    plan = MeituanItineraryParser().parse("请告诉我你的偏好。", start_date=date(2026, 9, 13), day_count=2, default_city="广州")

    assert not plan.items
    assert "无法核算预算" in plan.warning


def test_parser_normalizes_the_official_day_and_markdown_link_response_shape():
    content = """
## ✈️ 交通推荐
[火车 贵阳北→开封北 ¥826](http://example.test/go)
[火车 开封北→遵义 ¥767](http://example.test/back)

📝 DAY1：初抵汴梁
**下午**
乘 G320 次高铁于 10:15 从贵阳北出发，16:56 抵达开封北。
**晚上**
[鼓楼夜市](http://example.test/night)
开封烟火气的灵魂所在。
**晚餐**
[灌汤包](http://example.test/food)
皮薄馅多。

📝 DAY2：古城
**上午**
[开封府](http://example.test/scenic)
北宋首府官署遗址。

## 🏨 住宿方案
[果果民宿（开封鼓楼广场店）](http://example.test/hotel) **¥141起**
"""
    plan = MeituanItineraryParser().parse(content, start_date=date(2026, 8, 16), day_count=2, default_city="开封市")

    assert [item.name for item in plan.items] == [
        "去程高铁：乘 G320 次高铁于 10:15 从贵阳北出发，16:56 抵达开封北。",
        "鼓楼夜市",
        "灌汤包",
        "入住：果果民宿（开封鼓楼广场店）",
        "开封府",
        "火车 开封北→遵义 ¥767",
    ]
    assert plan.budget["breakdown"] == {"transport": 1593, "lodging": 141, "scenic": 0, "food": 0, "other": 0}
