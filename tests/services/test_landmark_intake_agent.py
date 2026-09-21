"""一键入库 Agent：编排流程、数据护栏与去重，全部离线。"""

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.models.enums import VerificationStatus
from app.services.landmark_intake_agent import (
    LandmarkIntakeAgent,
    LandmarkIntakeDuplicate,
    LandmarkIntakeError,
    LandmarkIntakeUnavailable,
)

LONG_DESCRIPTION = (
    "在作品中，小西天是主角取经路上的重要场景。\n"
    "游戏里主要出现于第二章末尾，玩家在此经历关键战斗情节。\n"
    "现实中的小西天位于山西省隰县，明代悬塑闻名于世，是全国重点文物保护单位。"
)

COMPOSE_PAYLOAD = {
    "ip_type": "game",
    "work_title": "黑神话：悟空",
    "aliases": "Black Myth",
    "landmark_name": "小西天",
    "landmark_kind": "古建筑",
    "country_code": "CN",
    "country_name": "中国",
    "province_name": "山西省",
    "city_name": "临汾市",
    "district_name": "隰县",
    "normalized_address": "山西省临汾市隰县凤山小西天",
    "description": LONG_DESCRIPTION,
    "transit_text": "临汾乘车至隰县后步行可达。",
    "source_url": "https://news.example/xiaoxitian",
    "source_title": "小西天报道",
    "source_publisher": "示例新闻",
    "source_type": "news",
}

REFERENCES = [
    {"title": "隰县小西天游记", "url": "https://news.example/xiaoxitian", "snippet": "悬塑之美"},
    {"title": "官方取景地介绍", "url": "https://official.example/list", "snippet": "官方取景列表"},
]


class FakeLLM:
    def __init__(self, parse_payload, compose_payload):
        self.parse_payload = parse_payload
        self.compose_payload = compose_payload
        self.compose_prompts = []

    def generate_json(self, messages, **kwargs):
        content = messages[1]["content"]
        if content.startswith("用户输入："):
            return self.parse_payload
        self.compose_prompts.append(content)
        return self.compose_payload


class FakeSearch:
    def __init__(self, references=(), error=None):
        self.references = list(references)
        self.error = error
        self.queries = []

    def discover(self, template, query):
        self.queries.append((template, query))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            id=42,
            references=[
                SimpleNamespace(title=item["title"], url=item["url"], snippet=item["snippet"])
                for item in self.references
            ],
        )


class FakeGeocoder:
    def __init__(self, coords=None):
        self.coords = coords
        self.calls = []

    def geocode(self, country_code, address, city=None):
        self.calls.append((country_code, address, city))
        return self.coords


def build_agent(db, parse=None, compose=None, search=None, geocoder=None, llm=None):
    settings = get_settings()
    fake_llm = llm or FakeLLM(
        parse or {"ip_type": "game", "work_title": "黑神话：悟空", "aliases": "", "landmark_name": "小西天",
                  "landmark_kind": "古建筑", "notes": ""},
        compose or dict(COMPOSE_PAYLOAD),
    )
    return LandmarkIntakeAgent(
        db,
        settings,
        llm=fake_llm,
        search_service=search if search is not None else FakeSearch(references=REFERENCES),
        geocoder=geocoder if geocoder is not None else FakeGeocoder(coords=(36.0667, 110.9389)),
    )


def test_intake_creates_candidate_with_references_and_coordinates(db_session):
    outcome = build_agent(db_session).intake("黑神话悟空里的小西天")

    assert outcome.landmark_id > 0
    assert outcome.search_run_id == 42
    assert outcome.latitude == pytest.approx(36.0667)
    assert [step.status for step in outcome.steps] == ["ok", "ok", "ok", "ok", "ok"]
    assert outcome.warnings == []

    from sqlalchemy import select
    from app.models.landmark import Landmark

    landmark = db_session.get(Landmark, outcome.landmark_id)
    assert landmark.verification_status is VerificationStatus.CANDIDATE
    assert landmark.published_at is None
    assert landmark.location.latitude == pytest.approx(36.0667)
    assert landmark.sources[0].source.url == "https://news.example/xiaoxitian"


def test_source_url_outside_references_is_replaced(db_session):
    compose = dict(COMPOSE_PAYLOAD)
    compose["source_url"] = "https://fabricated.example/not-in-list"
    agent = build_agent(db_session, compose=compose)

    outcome = agent.intake("黑神话悟空 小西天")

    from app.models.landmark import Landmark

    landmark = db_session.get(Landmark, outcome.landmark_id)
    assert landmark.sources[0].source.url == REFERENCES[0]["url"]
    assert any("不在检索结果中" in warning for warning in outcome.warnings)


def test_compose_prompt_must_carry_reference_urls(db_session):
    agent = build_agent(db_session)
    agent.intake("黑神话悟空 小西天")

    llm = agent._llm
    prompt = llm.compose_prompts[0]
    assert "https://news.example/xiaoxitian" in prompt
    assert "只能从这里逐字选择" in prompt


def test_search_failure_degrades_with_warning(db_session):
    from app.integrations.search.bocha_web_search import SearchProviderError

    search = FakeSearch(error=SearchProviderError("boom"))
    outcome = build_agent(db_session, search=search).intake("黑神话悟空 小西天")

    assert outcome.search_run_id is None
    assert any("联网检索不可用" in warning for warning in outcome.warnings)
    assert outcome.landmark_id > 0


def test_geocode_failure_leaves_coordinates_empty(db_session):
    outcome = build_agent(db_session, geocoder=FakeGeocoder(coords=None)).intake("黑神话悟空 小西天")

    assert outcome.latitude is None
    assert any("坐标" in warning for warning in outcome.warnings)
    from app.models.landmark import Landmark

    landmark = db_session.get(Landmark, outcome.landmark_id)
    assert landmark.location.latitude is None


def test_missing_llm_key_raises_unavailable(db_session):
    agent = LandmarkIntakeAgent(db_session, get_settings())
    with pytest.raises(LandmarkIntakeUnavailable):
        agent.intake("黑神话悟空 小西天")


def test_duplicate_work_landmark_address_is_rejected(db_session):
    from tests.factories import create_landmark

    create_landmark(db_session, published=False, work_title="黑神话：悟空", landmark_name="小西天")
    compose = dict(COMPOSE_PAYLOAD)
    compose["normalized_address"] = "山西省朔州市小西天"
    compose["city_name"] = "朔州市"
    agent = build_agent(db_session, compose=compose)

    with pytest.raises(LandmarkIntakeDuplicate):
        agent.intake("黑神话悟空 小西天")


def test_short_description_is_rejected(db_session):
    compose = dict(COMPOSE_PAYLOAD)
    compose["description"] = "太短的简介。"
    with pytest.raises(LandmarkIntakeError):
        build_agent(db_session, compose=compose).intake("黑神话悟空 小西天")


def test_unrecognized_ip_type_is_rejected(db_session):
    parse = {"ip_type": "music", "work_title": "某专辑", "aliases": "", "landmark_name": "某地", "notes": ""}
    with pytest.raises(LandmarkIntakeError, match="作品类型"):
        build_agent(db_session, parse=parse).intake("某专辑 某地")


def test_blank_input_is_rejected(db_session):
    with pytest.raises(LandmarkIntakeError):
        build_agent(db_session).intake("   ")
