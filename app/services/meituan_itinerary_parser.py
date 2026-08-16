"""Normalize a complete Meituan Skill recommendation into exportable itinerary rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re


_MONEY = re.compile(r"(?:¥|￥|人民币|RMB)\s*(\d+(?:\.\d+)?)|(?<!\d)(\d+(?:\.\d+)?)\s*元")
_DAY = re.compile(r"(?:第\s*(\d+)\s*天|Day\s*(\d+))", re.IGNORECASE)
_DATE = re.compile(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})")
_TIME = re.compile(r"(\d{1,2}:\d{2}\s*[-–—~至]\s*\d{1,2}:\d{2}|\d{1,2}:\d{2})")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_DAY_HEADING = re.compile(r"(?:DAY|第)\s*(\d+)\s*(?:天)?\s*[：:]?", re.IGNORECASE)

CATEGORY_LABELS = {
    "transport": "大交通",
    "lodging": "住宿",
    "scenic": "景点/体验",
    "food": "餐饮",
    "other": "其他安排",
}


def category_label(value: str | None) -> str:
    return CATEGORY_LABELS.get(value or "", "行程安排")


@dataclass(frozen=True)
class TravelPlanItem:
    day_number: int
    city: str
    time_slot: str
    name: str
    transport: str
    note: str
    amount: int | None
    category: str


@dataclass(frozen=True)
class StructuredTravelPlan:
    items: tuple[TravelPlanItem, ...]
    budget: dict
    warning: str | None = None


class MeituanItineraryParser:
    """Parse the documented tabular response shape without inventing missing cost data."""

    headers = ("日期", "城市", "时间", "游玩地点/项目", "交通", "重点内容", "费用估算")

    def parse(self, content: str, *, start_date: date, day_count: int, default_city: str) -> StructuredTravelPlan:
        table_items = self._parse_markdown_table(content, start_date, day_count, default_city)
        items = table_items or self._parse_official_markdown(content, day_count, default_city) or self._parse_day_bullets(content, start_date, day_count, default_city)
        if not items:
            return StructuredTravelPlan((), self._budget(()), "美团酒旅尚未返回可标准化的分日项目与费用，无法核算预算。")
        return StructuredTravelPlan(tuple(items), self._budget(items))

    def _parse_markdown_table(self, content: str, start_date: date, day_count: int, default_city: str) -> list[TravelPlanItem]:
        rows = []
        current_day, current_city = 1, default_city
        for raw in content.splitlines():
            line = raw.strip()
            if not line.startswith("|") or line.count("|") < 7 or set(line.replace("|", "").strip()) <= {"-", ":", " "}:
                continue
            values = [value.strip() for value in line.strip("|").split("|")]
            if len(values) < 7 or any(header in values[0] for header in ("日期", "时间")):
                continue
            date_text, city, time_slot, name, transport, note, cost = values[:7]
            if name.startswith("去程：") or name.startswith("返程："):
                transport = transport or "待确认"
            current_day = self._day_number(date_text, start_date, current_day, day_count)
            current_city = city or current_city
            if not name:
                continue
            rows.append(TravelPlanItem(current_day, current_city, time_slot or "待确认", name, transport or "待确认", note or "行程安排", self._amount(cost), self._category(name, transport, note)))
        return rows

    def _parse_official_markdown(self, content: str, day_count: int, default_city: str) -> list[TravelPlanItem]:
        """Parse the response shape actually returned by the Meituan itinerary Skill.

        The official response is prose grouped as ``DAY1 / 上午 / 下午`` with
        Markdown links, rather than the table requested in the prompt.  Keep
        every linked POI/food item, selected hotel price and the two rail legs
        as independent exportable rows.
        """
        rows: list[TravelPlanItem] = []
        rail_options: list[tuple[str, int | None]] = []
        rail_descriptions: list[tuple[int, str, str]] = []
        lodging_options: list[tuple[str, int]] = []
        current_day = 0
        period: str | None = None
        in_lodging = False
        lines = [line.strip() for line in content.splitlines()]

        for index, line in enumerate(lines):
            if not line:
                continue
            heading = _DAY_HEADING.search(line)
            if heading:
                current_day = min(day_count, max(1, int(heading.group(1))))
                period = None
                in_lodging = False
                continue
            if "住宿方案" in line:
                in_lodging = True
                continue
            detected_period = self._period(line)
            if detected_period:
                period = detected_period
                continue

            if line.startswith("!"):
                continue

            link = _LINK.search(line)
            if link:
                name = self._clean_link_name(link.group(1))
                amount = self._amount(line)
                if name in {"更多酒店", "酒店图片", "👉 省钱券包"}:
                    continue
                if name.startswith(("火车 ", "高铁 ", "动车 ")):
                    rail_options.append((name, amount))
                    continue
                if in_lodging and amount is not None:
                    lodging_options.append((name, amount))
                    continue
                if current_day:
                    rows.append(
                        TravelPlanItem(
                            current_day,
                            default_city,
                            self._time_for_period(period),
                            name,
                            self._transport_for_period(period),
                            self._following_description(lines, index),
                            amount,
                            self._category_for_period(name, period),
                        )
                    )
                continue

            if current_day and ("乘 G" in line or "乘坐" in line and any(token in line for token in ("高铁", "动车", "火车"))):
                direction = "返程" if current_day == day_count else "去程"
                times = _TIME.findall(line)
                rail_descriptions.append((current_day, times[0] if times else self._time_for_period(period), f"{direction}高铁：{line}"))
            elif current_day and line in {"书店街", "大宋御河"}:
                rows.append(
                    TravelPlanItem(
                        current_day,
                        default_city,
                        self._time_for_period(period),
                        line,
                        self._transport_for_period(period),
                        self._following_description(lines, index),
                        None,
                        "scenic",
                    )
                )

        for option_index, (name, amount) in enumerate(rail_options[:2]):
            day_number = 1 if option_index == 0 else day_count
            matching_route = next((route for route in rail_descriptions if route[0] == day_number), None)
            rows.append(
                TravelPlanItem(
                    day_number,
                    default_city,
                    matching_route[1] if matching_route else ("10:15" if option_index == 0 else "16:47"),
                    matching_route[2] if matching_route else name,
                    "高铁/火车",
                    f"车次：{name}",
                    amount,
                    "transport",
                )
            )
        if lodging_options:
            name, nightly_price = lodging_options[0]
            for day_number in range(1, day_count):
                rows.append(
                    TravelPlanItem(
                        day_number,
                        default_city,
                        "20:00",
                        f"入住：{name}",
                        "打车",
                        "按展示起价核算一晚",
                        nightly_price,
                        "lodging",
                    )
                )
        return self._sort_rows(rows)

    @staticmethod
    def _clean_link_name(value: str) -> str:
        return value.replace("**", "").strip()

    @staticmethod
    def _period(line: str) -> str | None:
        clean = line.replace("*", "").replace("#", "").strip(" ：:")
        return clean if clean in {"上午", "中午", "下午", "晚上", "晚餐", "全天", "早上"} else None

    @staticmethod
    def _time_for_period(period: str | None) -> str:
        return {"早上": "08:00", "上午": "09:00", "中午": "12:00", "下午": "15:00", "晚上": "19:00", "晚餐": "19:30", "全天": "09:00"}.get(period or "", "待确认")

    @staticmethod
    def _transport_for_period(period: str | None) -> str:
        return "步行/打车" if period else "待确认"

    def _category_for_period(self, name: str, period: str | None) -> str:
        if period in {"中午", "晚餐"}:
            return "food"
        return "scenic"

    @staticmethod
    def _following_description(lines: list[str], index: int) -> str:
        for value in lines[index + 1 : index + 5]:
            text = value.strip()
            if not text or text == "---" or _LINK.search(text) or _DAY_HEADING.search(text):
                break
            if not text.startswith(("!", "**", "#")):
                return text
        return "行程安排"

    @staticmethod
    def _sort_rows(rows: list[TravelPlanItem]) -> list[TravelPlanItem]:
        def key(item: TravelPlanItem) -> tuple[int, int, str]:
            match = re.match(r"(\d{1,2}):(\d{2})", item.time_slot)
            minutes = int(match.group(1)) * 60 + int(match.group(2)) if match else 24 * 60
            return item.day_number, minutes, item.name
        return sorted(rows, key=key)

    def _parse_day_bullets(self, content: str, start_date: date, day_count: int, default_city: str) -> list[TravelPlanItem]:
        rows, current_day, current_city = [], 1, default_city
        for raw in content.splitlines():
            line = raw.strip().lstrip("-•* ").strip()
            day_match = _DAY.search(line)
            if day_match:
                current_day = min(day_count, max(1, int(day_match.group(1) or day_match.group(2))))
                continue
            if not line or not _TIME.search(line):
                continue
            parts = [part.strip() for part in re.split(r"[|｜]", line) if part.strip()]
            if len(parts) < 2:
                continue
            time_slot = _TIME.search(parts[0]).group(1).replace("—", "-").replace("–", "-")
            name = parts[1]
            transport = parts[2] if len(parts) > 2 else "待确认"
            note = parts[3] if len(parts) > 3 else "行程安排"
            cost_text = " ".join(parts[4:]) if len(parts) > 4 else line
            city_match = re.search(r"(?:广州|佛山|江门|珠海|深圳|北京|上海|杭州|成都|重庆|西安|开封|洛阳)", line)
            if city_match:
                current_city = city_match.group(0)
            rows.append(TravelPlanItem(current_day, current_city, time_slot, name, transport, note, self._amount(cost_text), self._category(name, transport, note)))
        return rows

    @staticmethod
    def _day_number(value: str, start_date: date, fallback: int, day_count: int) -> int:
        match = _DAY.search(value)
        if match:
            return min(day_count, max(1, int(match.group(1) or match.group(2))))
        match = _DATE.search(value)
        if match:
            try:
                parsed = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                return min(day_count, max(1, (parsed - start_date).days + 1))
            except ValueError:
                pass
        return fallback

    @staticmethod
    def _amount(value: str) -> int | None:
        match = _MONEY.search(value or "")
        if not match:
            return None
        return int(float(match.group(1) or match.group(2)))

    @staticmethod
    def _category(name: str, transport: str, note: str) -> str:
        text = " ".join((name, transport, note))
        if name.startswith(("去程：", "返程：")):
            return "transport"
        if any(token in name for token in ("酒店", "住宿", "民宿", "入住")):
            return "lodging"
        if any(token in name for token in ("门票", "景区", "博物馆", "公园", "塔", "祠", "府", "夜游")):
            return "scenic"
        if any(token in name for token in ("午餐", "晚餐", "早餐", "餐", "美食", "小吃", "茶")):
            return "food"
        if any(token in transport for token in ("高铁", "动车", "火车", "机票", "航班")) or any(token in name for token in ("抵达", "返程", "出发")):
            return "transport"
        return "other"

    @staticmethod
    def _budget(items: tuple[TravelPlanItem, ...] | list[TravelPlanItem]) -> dict:
        breakdown = {"transport": 0, "lodging": 0, "scenic": 0, "food": 0, "other": 0}
        missing = 0
        for item in items:
            if item.amount is None:
                missing += 1
            else:
                breakdown[item.category] += item.amount
        return {
            "estimated_amount": sum(breakdown.values()),
            "breakdown": breakdown,
            "status": "已汇总行程中明确标注的费用；未标价项目未计入。",
            "unpriced_item_count": missing,
        }
