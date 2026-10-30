"""Read community-maintained local landmark album metadata safely.

相册归属键为 ``landmark:<landmark_id>``（本地数据库的稳定主键）。旧版用
``<ip_type>:<地标名称>``，改名即丢图，且同类型同名地标会互相串图。

旧键仅作为临时兼容读取路径保留：真实历史 manifest 的迁移需另行授权
（见 ``scripts/migrate_album_keys.py``，默认只读 dry-run）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from threading import Lock

from app.models.enums import IPType


ALBUM_ROOT = "data/contributions/landmark_albums"
ALBUM_PUBLIC_PREFIX = "/contributions/landmark-albums/images"
ALLOWED_EXTENSIONS = {".avif", ".jpeg", ".jpg", ".png", ".webp"}

_manifest_cache: dict[tuple[str, int, int], dict[str, object]] = {}
_cache_lock = Lock()


def album_key(landmark_id: int) -> str:
    """稳定相册键：只依赖数据库主键，改名不影响归属。"""
    return f"landmark:{landmark_id}"


def legacy_album_key(ip_type: IPType | str, landmark_name: str) -> str:
    value = ip_type.value if isinstance(ip_type, IPType) else str(ip_type)
    return f"{value}:{landmark_name}"


@dataclass(frozen=True)
class AlbumPhoto:
    url: str
    alt: str
    caption: str | None
    credit: str | None
    license_note: str | None
    source_url: str | None


class LandmarkAlbumService:
    """Loads one album without coupling community media to the database schema."""

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._manifest_path = project_root / ALBUM_ROOT / "manifest.json"

    def first_photo_url(
        self,
        landmark_id: int,
        *,
        ip_type: IPType | None = None,
        landmark_name: str | None = None,
    ) -> str | None:
        photos = self.get_photos(landmark_id, ip_type=ip_type, landmark_name=landmark_name)
        return photos[0].url if photos else None

    def get_photos(
        self,
        landmark_id: int,
        *,
        ip_type: IPType | None = None,
        landmark_name: str | None = None,
    ) -> tuple[AlbumPhoto, ...]:
        """读取相册；新键优先，旧键仅在迁移完成前作为兼容路径。"""
        albums = self._read_manifest().get("albums", {})
        if not isinstance(albums, dict):
            return ()
        candidates = albums.get(album_key(landmark_id))
        if not isinstance(candidates, list):
            if ip_type is None or not landmark_name:
                return ()
            # 临时兼容：真实历史数据尚未获授权迁移时保留旧键读取。
            candidates = albums.get(legacy_album_key(ip_type, landmark_name), [])
        if not isinstance(candidates, list):
            return ()
        return self._to_photos(candidates)

    def entries_for_key(self, key: str) -> list[dict]:
        albums = self._read_manifest().get("albums", {})
        if not isinstance(albums, dict):
            return []
        entries = albums.get(key, [])
        return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []

    def album_keys(self) -> tuple[str, ...]:
        albums = self._read_manifest().get("albums", {})
        return tuple(albums) if isinstance(albums, dict) else ()

    def _to_photos(self, candidates: list) -> tuple[AlbumPhoto, ...]:
        photos: list[AlbumPhoto] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            relative_file = item.get("file")
            alt = item.get("alt")
            if not isinstance(relative_file, str) or not self._is_safe_image_path(relative_file):
                continue
            if not isinstance(alt, str) or not alt.strip():
                continue
            photos.append(
                AlbumPhoto(
                    url=f"{ALBUM_PUBLIC_PREFIX}/{relative_file}",
                    alt=alt.strip(),
                    caption=self._optional_text(item.get("caption")),
                    credit=self._optional_text(item.get("credit")),
                    license_note=self._optional_text(item.get("license")),
                    source_url=self._optional_url(item.get("source_url")),
                )
            )
        return tuple(photos)

    def _read_manifest(self) -> dict[str, object]:
        """按文件 mtime/size 缓存：提交后 manifest 变化会自动失效。"""
        try:
            stat = self._manifest_path.stat()
        except FileNotFoundError:
            return {}
        key = (str(self._manifest_path), stat.st_mtime_ns, stat.st_size)
        with _cache_lock:
            cached = _manifest_cache.get(key)
        if cached is not None:
            return cached
        try:
            raw = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        manifest = raw if isinstance(raw, dict) else {}
        with _cache_lock:
            _manifest_cache.clear()  # 只保留当前版本，避免无界增长
            _manifest_cache[key] = manifest
        return manifest

    @staticmethod
    def _is_safe_image_path(value: str) -> bool:
        path = PurePosixPath(value)
        return not path.is_absolute() and ".." not in path.parts and path.suffix.lower() in ALLOWED_EXTENSIONS

    @staticmethod
    def _optional_text(value: object) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _optional_url(value: object) -> str | None:
        return value if isinstance(value, str) and value.startswith(("https://", "http://")) else None
