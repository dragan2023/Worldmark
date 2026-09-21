"""Client for Bocha AI's Image Search API.

注意：博查当前（2026-08 实测）未提供独立的图片搜索端点，
`/v1/images/search` 与 `/v1/image/search` 均返回 404，仅 web-search 可用。
本客户端保留以兼容未来博查开放图片 API 时启用；相册 AI 找图的默认
图片来源为 `wikimedia_commons`（免 Key、免费授权、自带署名元数据）。

与 BochaWebSearchProvider 同一鉴权与错误口径：未配置 Key 抛
SearchConfigurationError，上游失败抛 SearchProviderError。返回的候选只带
元数据（链接、标题、来源页），由上层服务负责下载与内容校验。
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

import httpx

from app.integrations.search.bocha_web_search import SearchConfigurationError, SearchProviderError


@dataclass(frozen=True)
class ImageCandidate:
    """One image hit returned by the image search API."""

    image_url: str
    title: str
    source_page_url: str | None = None
    width: int | None = None
    height: int | None = None
    license: str | None = None  # 已知授权时填写（如 Commons 的 CC 许可）
    artist: str | None = None  # 已知作者/署名时填写


@dataclass(frozen=True)
class ImageSearchResult:
    request_id: str | None
    candidates: tuple[ImageCandidate, ...]


class BochaImageSearchProvider:
    """Retrieve image candidates from Bocha without involving an LLM."""

    name = "bocha_image_search"
    endpoint = "https://api.bochaai.com/v1/images/search"

    def __init__(self, api_key: str | None, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._transport = transport

    def search(self, query: str, count: int = 6) -> ImageSearchResult:
        if not self._api_key:
            raise SearchConfigurationError("BOCHA_API_KEY is not configured.")
        normalized = query.strip()
        if not normalized:
            raise ValueError("Image search query cannot be empty.")

        payload = {"query": normalized, "count": max(1, min(count, 20))}
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=20.0, transport=self._transport, trust_env=False) as client:
                response = client.post(self.endpoint, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchProviderError("Bocha image search request failed.") from exc

        body = response.json()
        if body.get("code") not in (None, 200):
            raise SearchProviderError(str(body.get("msg") or "Bocha image search returned an error."))
        data = body.get("data") or body
        pages = data.get("webPages") or {}
        items = pages.get("value") or []
        return ImageSearchResult(
            request_id=str(body.get("log_id") or "") or None,
            candidates=tuple(item for item in (self._parse_candidate(raw) for raw in items) if item is not None),
        )

    @staticmethod
    def _parse_candidate(item: Mapping[str, object]) -> ImageCandidate | None:
        image_url = ""
        for key in ("imageUrl", "image", "thumbnailUrl", "thumbnail", "url"):
            value = item.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                image_url = value
                break
        if not image_url:
            return None
        title = str(item.get("name") or item.get("title") or "未命名图片")
        page = item.get("url") or item.get("sourceUrl") or item.get("host")
        page_url = page if isinstance(page, str) and page.startswith(("http://", "https://")) else None
        width = BochaImageSearchProvider._optional_int(item.get("width"))
        height = BochaImageSearchProvider._optional_int(item.get("height"))
        return ImageCandidate(image_url=image_url, title=title, source_page_url=page_url, width=width, height=height)

    @staticmethod
    def _optional_int(value: object) -> int | None:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
