import subprocess

import httpx
import pytest

from app.integrations.amap_web_service import AmapConfigurationError, AmapWebService
from app.integrations.meituan_travel_mcp import MeituanMcpError, MeituanMcpUnavailable, MeituanTravelMcp


def test_amap_web_service_parses_poi_without_exposing_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/place/text"
        assert request.url.params["keywords"] == "应县木塔"
        assert request.url.params["city"] == "朔州"
        assert request.url.params["citylimit"] == "true"
        assert request.url.params["offset"] == "10"
        assert request.url.params["extensions"] == "base"
        return httpx.Response(200, json={"status": "1", "pois": [{"id": "poi-1", "name": "应县木塔", "address": "山西省朔州市", "location": "113.1,39.5"}]})

    client = AmapWebService("test-key", transport=httpx.MockTransport(handler))
    pois = client.search_poi("应县木塔", "朔州")

    assert pois[0].poi_id == "poi-1"
    assert pois[0].location == "113.1,39.5"


def test_amap_web_service_parses_poi_reference_cost_when_details_are_requested():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["extensions"] == "all"
        return httpx.Response(200, json={"status": "1", "pois": [{"id": "poi-1", "name": "酒店", "address": "地址", "biz_ext": {"cost": "258", "rating": "4.6"}}]})

    poi = AmapWebService("test-key", transport=httpx.MockTransport(handler)).search_poi("酒店", "开封", include_details=True)[0]
    assert poi.reference_cost == 258
    assert poi.rating == 4.6


def test_amap_web_service_uses_cost_field_for_walking_duration():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/direction/walking"
        assert request.url.params["show_fields"] == "cost"
        return httpx.Response(200, json={"status": "1", "route": {"paths": [{"distance": "860", "cost": {"duration": "720"}}]}})

    result = AmapWebService("test-key", transport=httpx.MockTransport(handler)).walking_distance("116.1,39.1", "116.2,39.2")
    assert result == {"distance_meters": 860, "duration_seconds": 720}


def test_amap_web_service_rejects_empty_poi_keywords():
    with pytest.raises(ValueError, match="keywords"):
        AmapWebService("test-key").search_poi("  ")


def test_amap_web_service_requires_key():
    with pytest.raises(AmapConfigurationError):
        AmapWebService(None).geocode("山西省朔州市")


def test_meituan_adapter_uses_official_skill_raw_json_contract(monkeypatch):
    adapter = MeituanTravelMcp("test-token", executable=None)
    monkeypatch.setattr(adapter, "_executable", None)
    with pytest.raises(MeituanMcpUnavailable, match="npx"):
        adapter.query("北京", "酒店")

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, '{"content":"北京行程建议"}', "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = MeituanTravelMcp("test-token", executable="npx").query("北京", "北京两日游", origin_query="我想去北京两日游")

    command, kwargs = calls[0]
    assert command == [
        "npx", "--yes", "@meituan-travel/ht-ai@latest", "query", "--query", "北京两日游",
        "--origin-query", "我想去北京两日游", "--channel", "meituan-developer", "--city", "北京", "-o", "json",
    ]
    assert kwargs["env"]["MEITUAN_HT_TOKEN"] == "test-token"
    assert kwargs["env"]["MEITUAN_RAW_JSON"] == "1"
    assert result.content == "北京行程建议"
    assert result.raw_json == {"content": "北京行程建议"}


def test_meituan_adapter_classifies_vendor_auth_timeout_and_bad_json(monkeypatch):
    adapter = MeituanTravelMcp("test-token", executable="npx", timeout_seconds=1)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 3, "", "auth failed"))
    with pytest.raises(MeituanMcpUnavailable, match="Token"):
        adapter.query("北京", "两日游")

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "not-json", ""))
    with pytest.raises(MeituanMcpError, match="JSON"):
        adapter.query("北京", "两日游")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(MeituanMcpError, match="超时"):
        adapter.query("北京", "两日游")
