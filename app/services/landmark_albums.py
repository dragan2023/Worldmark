"""Read community-maintained local landmark album metadata safely."""

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.models.enums import IPType


ALBUM_ROOT = "data/contributions/landmark_albums"
ALBUM_PUBLIC_PREFIX = "/contributions/landmark-albums/images"
ALLOWED_EXTENSIONS = {".avif", ".jpeg", ".jpg", ".png", ".webp"}


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
        self._manifest_path = project_root / ALBUM_ROOT / "manifest.json"
        self._manifest_cache: dict[str, object] | None = None

    def first_photo_url(self, ip_type: IPType, landmark_name: str) -> str | None:
        photos = self.get_photos(ip_type, landmark_name)
        return photos[0].url if photos else None

    def get_photos(self, ip_type: IPType, landmark_name: str) -> tuple[AlbumPhoto, ...]:
        manifest = self._read_manifest()
        candidates = manifest.get("albums", {}).get(f"{ip_type.value}:{landmark_name}", [])
        if not isinstance(candidates, list):
            return ()

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
        if self._manifest_cache is not None:
            return self._manifest_cache
        try:
            raw = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            self._manifest_cache = {}
        else:
            self._manifest_cache = raw if isinstance(raw, dict) else {}
        return self._manifest_cache

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
