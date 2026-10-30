"""Client for DeepSeek's Search & Fetch API.

``POST /v1/tools/search`` 返回排序后的网页引用，``POST /v1/tools/fetch``
把网页转成 Markdown 正文。两者与聊天接口共用同一个 ``DEEPSEEK_API_KEY``，
因此一个密钥同时覆盖「生成」与「联网检索」两条链路。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from app.integrations.search.base import (
    SearchConfigurationError,
    SearchProviderError,
    SearchReference,
    SearchResult,
)

# 接口硬限制：query 为 1～128 个 Unicode 字符。
_MAX_QUERY_CHARS = 128


@dataclass(frozen=True)
class FetchedPage:
    """One page converted to Markdown by ``/v1/tools/fetch``."""

    title: str
    content: str


class DeepSeekWebSearchProvider:
    """Retrieve ranked web references and page content from DeepSeek."""

    name = "deepseek_web_search"
    default_base_url = "https://api.deepseek.com"

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or self.default_base_url).rstrip("/")
        self._transport = transport

    def search(self, query: str, count: int = 8) -> SearchResult:
        if not self._api_key:
            raise SearchConfigurationError("DEEPSEEK_API_KEY is not configured.")
        payload = {
            "query": " ".join(query.split())[:_MAX_QUERY_CHARS],
            "count": max(1, min(count, 50)),
            # 只要 summary（600～800 字，给模型阅读）；正文按需另行 fetch。
            "need_content": False,
        }
        body = self._post("/v1/tools/search", payload)
        results = body.get("results") or []
        return SearchResult(
            request_id=None,
            references=tuple(self._parse_reference(item) for item in results),
        )

    def fetch(self, url: str) -> FetchedPage:
        if not self._api_key:
            raise SearchConfigurationError("DEEPSEEK_API_KEY is not configured.")
        body = self._post("/v1/tools/fetch", {"url": url})
        return FetchedPage(
            title=str(body.get("title") or ""),
            content=str(body.get("content") or ""),
        )

    def _post(self, path: str, payload: Mapping[str, object]) -> Mapping[str, object]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=20.0, transport=self._transport, trust_env=False) as client:
                response = client.post(self._base_url + path, headers=headers, json=dict(payload))
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchProviderError("DeepSeek 网页检索请求失败。") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise SearchProviderError("DeepSeek 返回了无法解析的响应。") from exc
        if not isinstance(body, Mapping):
            raise SearchProviderError("DeepSeek 返回了无法解析的响应。")
        return body

    @staticmethod
    def _parse_reference(item: Mapping[str, object]) -> SearchReference:
        title = str(item.get("title") or "Untitled source")
        url = str(item.get("url") or "")
        text = str(item.get("summary") or item.get("snippet") or "")
        return SearchReference(title=title, url=url, snippet=text or None)
