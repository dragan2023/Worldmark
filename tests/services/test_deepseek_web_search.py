import json

import httpx
import pytest

from app.core.config import Settings
from app.integrations.search.base import (
    SearchConfigurationError,
    SearchProviderError,
    SearchReference,
    SearchResult,
)
from app.integrations.search.deepseek_web_search import DeepSeekWebSearchProvider
from app.services.search_discovery import SearchDiscoveryService


def test_deepseek_provider_uses_tools_search_payload():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={
            "results": [{
                "rerank_score": 2.1,
                "title": "官方来源",
                "url": "https://example.org",
                "snippet": "短摘要",
                "summary": "长摘要（模型阅读）",
                "content": "",
                "site_name": "Example",
                "date": None,
                "authority": 3,
            }],
        })

    provider = DeepSeekWebSearchProvider("test-key", transport=httpx.MockTransport(handler))
    result = provider.search('"示例游戏" 取景地 官方')

    assert captured["url"] == "https://api.deepseek.com/v1/tools/search"
    assert captured["payload"] == {
        "query": '"示例游戏" 取景地 官方',
        "count": 8,
        "need_content": False,
    }
    assert result.references[0].url == "https://example.org"
    # 优先把 summary 交给模型；缺失时才退回 snippet
    assert result.references[0].snippet == "长摘要（模型阅读）"


def test_deepseek_provider_truncates_query_to_api_limit():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"results": []})

    DeepSeekWebSearchProvider("k", transport=httpx.MockTransport(handler)).search("字" * 300)

    assert len(captured["payload"]["query"]) == 128


def test_deepseek_provider_requires_local_key():
    with pytest.raises(SearchConfigurationError):
        DeepSeekWebSearchProvider(None).search("test")


def test_deepseek_fetch_returns_markdown():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/v1/tools/fetch")
        assert json.loads(request.content) == {"url": "https://example.org/a"}
        return httpx.Response(200, json={"title": "标题", "content": "# 正文"})

    page = DeepSeekWebSearchProvider("k", transport=httpx.MockTransport(handler)).fetch("https://example.org/a")

    assert (page.title, page.content) == ("标题", "# 正文")


def test_deepseek_provider_reports_upstream_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(SearchProviderError):
        DeepSeekWebSearchProvider("k", transport=httpx.MockTransport(handler)).search("x")


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
