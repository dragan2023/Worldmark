"""Wikimedia Commons 图片检索客户端（免 Key）。

Commons 是相册 AI 找图的默认来源：无需 API Key，返回的图片均为自由授权，
且随结果返回许可（LicenseShortName）与作者（Artist）元数据，可在下载前
就完成合规署名。请求走 Commons 的 MediaWiki API（generator=search 检索
File 命名空间），并优先使用 1600px 缩略图以控制下载体积。

礼貌性要求：MediaWiki API 要求可联系的 User-Agent；此处固定 UA，请勿在
生产中移除。
"""

from __future__ import annotations

from collections.abc import Mapping
import html
import re

import httpx

from app.integrations.search.bocha_image_search import ImageCandidate, ImageSearchResult

ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}
_TAG_PATTERN = re.compile(r"<[^>]+>")


def _strip_html(value: str) -> str:
    return html.unescape(_TAG_PATTERN.sub("", value)).strip()


class WikimediaCommonsImageProvider:
    """Search freely-licensed images on Wikimedia Commons."""

    name = "wikimedia_commons"
    endpoint = "https://commons.wikimedia.org/w/api.php"
    user_agent = "WorldmarkAlbumEditor/1.0 (https://github.com/dragan2023/Worldmark; contact via repository issues)"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def search(self, query: str, count: int = 6) -> ImageSearchResult:
        normalized = query.strip()
        if not normalized:
            raise ValueError("Commons search query cannot be empty.")
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": normalized,
            "gsrnamespace": "6",
            "gsrlimit": str(max(1, min(count * 2, 12))),
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": "1600",
        }
        # trust_env 保持 True：本地网络可能依赖系统代理环境变量访问 Commons
        last_error: Exception | None = None
        for attempt in range(2):  # 网络抖动（握手超时）时重试一次
            try:
                with httpx.Client(
                    timeout=30.0, transport=self._transport, trust_env=True, headers={"User-Agent": self.user_agent}
                ) as client:
                    response = client.get(self.endpoint, params=params)
                    response.raise_for_status()
                break
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == 1:
                    raise RuntimeError(f"Commons 检索请求失败：{exc}") from exc

        body = response.json()
        pages = (body.get("query") or {}).get("pages") or {}
        candidates: list[ImageCandidate] = []
        for page in pages.values():
            candidate = self._parse_page(page)
            if candidate is not None:
                candidates.append(candidate)
        candidates.sort(key=lambda item: item.title)
        return ImageSearchResult(request_id=None, candidates=tuple(candidates[: max(1, min(count, 12))]))

    def _parse_page(self, page: Mapping[str, object]) -> ImageCandidate | None:
        infos = page.get("imageinfo") or []
        if not infos or not isinstance(infos[0], Mapping):
            return None
        info = infos[0]
        mime = str(info.get("mime") or "")
        if mime not in ALLOWED_MIMES:
            return None
        image_url = str(info.get("thumburl") or info.get("url") or "")
        if not image_url.startswith(("http://", "https://")):
            return None
        title = str(page.get("title") or "未命名图片").removeprefix("File:").strip()
        metadata = info.get("extmetadata") or {}
        license_name = self._metadata_value(metadata, "LicenseShortName")
        artist = self._metadata_value(metadata, "Artist") or self._metadata_value(metadata, "Credit")
        page_url = info.get("descriptionurl")
        return ImageCandidate(
            image_url=image_url,
            title=title,
            source_page_url=str(page_url) if isinstance(page_url, str) and page_url.startswith("http") else None,
            width=self._optional_int(info.get("thumbwidth") or info.get("width")),
            height=self._optional_int(info.get("thumbheight") or info.get("height")),
            license=license_name or None,
            artist=artist or None,
        )

    @staticmethod
    def _metadata_value(metadata: Mapping[str, object], key: str) -> str:
        entry = metadata.get(key)
        if isinstance(entry, Mapping):
            value = entry.get("value")
            if isinstance(value, str) and value.strip():
                return _strip_html(value)[:200]
        return ""

    @staticmethod
    def _optional_int(value: object) -> int | None:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
