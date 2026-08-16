import json

import httpx
import pytest

from app.core.config import Settings
from app.integrations.search.base import SearchReference, SearchResult
from app.integrations.search.bocha_web_search import BochaWebSearchProvider, SearchConfigurationError
from app.services.search_discovery import SearchDiscoveryService


def test_bocha_provider_uses_official_web_search_payload():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={
            "code": 200,
            "log_id": "log-1",
            "data": {"webPages": {"value": [{
                "name": "官方来源", "url": "https://example.org", "snippet": "候选摘要", "summary": "补充摘要",
            }]}},
        })

    provider = BochaWebSearchProvider("test-key", transport=httpx.MockTransport(handler))
    result = provider.search('"示例游戏" 取景地 官方')

    assert result.request_id == "log-1"
    assert result.references[0].url == "https://example.org"
    assert result.references[0].snippet == "候选摘要\n补充摘要"
    assert captured["payload"] == {
        "query": '"示例游戏" 取景地 官方',
        "freshness": "oneYear",
        "summary": True,
        "count": 8,
    }


def test_bocha_provider_requires_local_key():
    with pytest.raises(SearchConfigurationError):
        BochaWebSearchProvider(None).search("test")


def test_discovery_records_references_without_daily_quota(db_session):
    class FakeProvider:
        name = "fake"

        def __init__(self) -> None:
            self._call_number = 0

        def search(self, query: str) -> SearchResult:
            self._call_number += 1
            return SearchResult(f"request-{self._call_number}", (SearchReference("官方来源", "https://example.org", "摘要"),))

    service = SearchDiscoveryService(db_session, settings=Settings(), provider=FakeProvider())
    search_run = service.discover("{作品名称} 官方", "示例作品 官方")
    second = service.discover("{作品名称} 官方", "第二个查询")

    assert search_run.result_count == 1
    assert search_run.references[0].url == "https://example.org"
    assert second.id != search_run.id
