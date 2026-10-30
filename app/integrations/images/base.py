"""Image-search value objects shared by every image provider."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImageCandidate:
    """One image hit returned by an image search API."""

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
