"""地标相册编辑服务：暂存区（用户上传 + AI 下载）与提交落库。

数据流：

1. 用户上传或 AI 下载的图片先落在暂存区 `uploads/landmark_albums/{landmark_id}/`，
   通过 `/staging/landmark-albums` 静态目录预览；此阶段不入正式相册；
2. 编辑器把「已发布照片 + 暂存照片」合并为工作集，用户可点 X 剔除、
   点小图放大并编辑 alt/caption/credit/license/source_url；
3. 提交时：暂存文件移入正式相册目录、被移除的已发布照片移入回收站
   `_trash/`，随后原子化重写 manifest.json 中该地标的相册条目。

版权口径：AI 下载的图片默认标记「网络检索图片，版权待确认」，用户上传默认
「用户自传，自行确认版权」；提交后才会对外展示，展示即代表维护者确认可用。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from datetime import UTC, datetime
import json
import os
import re
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.integrations.deepseek_client import DeepSeekClient
from app.models.landmark import Landmark
from app.services.landmark_albums import (
    ALBUM_PUBLIC_PREFIX,
    ALBUM_ROOT,
    ALLOWED_EXTENSIONS,
)

STAGING_ROOT = "uploads/landmark_albums"
STAGING_PUBLIC_PREFIX = "/staging/landmark-albums"
TRASH_DIR_NAME = "_trash"

ALLOWED_IMAGE_MIMES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/avif": ".avif"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_AI_DOWNLOADS = 6
_STAGED_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
_DEFAULT_LICENSE_BY_KIND = {
    "upload": "用户自传，自行确认版权",
    "ai": "网络检索图片，版权待确认",
}


@dataclass(frozen=True)
class StagedPhoto:
    """One image waiting in the staging area."""

    kind: str  # upload | ai
    file: str
    url: str
    alt: str
    caption: str | None = None
    credit: str | None = None
    license: str = ""
    source_url: str | None = None


@dataclass(frozen=True)
class DownloadOutcome:
    saved: tuple[StagedPhoto, ...]
    failures: tuple[dict[str, str], ...]
    queries: tuple[str, ...]
    notices: tuple[str, ...] = ()


class AlbumEditorError(RuntimeError):
    """Generic editor failure with a user-facing message."""


class LandmarkAlbumNotFound(AlbumEditorError):
    """The landmark does not exist."""


class StagingNotFoundError(AlbumEditorError):
    """The staged file is gone (already submitted or removed elsewhere)."""


class LandmarkAlbumEditorService:
    def __init__(
        self,
        db: Session,
        project_root,
        *,
        settings: Settings,
        llm: DeepSeekClient | None = None,
        image_provider=None,
        downloader=None,
    ) -> None:
        self._db = db
        self._project_root = project_root
        self._album_root = project_root / ALBUM_ROOT
        self._staging_root = project_root / STAGING_ROOT
        self._settings = settings
        self._llm = llm
        self._image_provider = image_provider
        self._downloader = downloader

    # ---------- 暂存区 ----------

    def staging_dir(self, landmark_id: int):
        directory = self._staging_root / str(landmark_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save_upload(self, landmark_id: int, filename: str, content: bytes, content_type: str | None, kind: str = "upload") -> StagedPhoto:
        if not content:
            raise AlbumEditorError("上传文件为空。")
        if len(content) > MAX_UPLOAD_BYTES:
            raise AlbumEditorError("单张图片不能超过 8MB。")
        extension = ALLOWED_IMAGE_MIMES.get((content_type or "").split(";")[0].strip().lower())
        if extension is None:
            raise AlbumEditorError("仅支持 JPG / PNG / WebP / AVIF 格式的图片。")
        staged_name = f"{kind}-{uuid.uuid4().hex[:12]}{extension}"
        self._write_staged(landmark_id, staged_name, content)
        return self._staged_photo(landmark_id, kind, staged_name)

    def list_staged(self, landmark_id: int) -> tuple[StagedPhoto, ...]:
        directory = self.staging_dir(landmark_id)
        photos = [
            self._staged_photo(landmark_id, self._kind_of(item.name), item.name)
            for item in sorted(directory.iterdir(), key=lambda entry: entry.stat().st_mtime)
            if item.is_file() and _STAGED_NAME_PATTERN.match(item.name)
            and item.suffix.lower() in ALLOWED_EXTENSIONS
        ]
        return tuple(photos)

    def delete_staged(self, landmark_id: int, file: str) -> None:
        target = self._resolve_staged_path(landmark_id, file)
        if not target.is_file():
            raise StagingNotFoundError("暂存图片不存在或已被删除。")
        target.unlink()
        self._drop_meta(landmark_id, file)

    def _resolve_staged_path(self, landmark_id: int, file: str):
        if not _STAGED_NAME_PATTERN.match(file or ""):
            raise AlbumEditorError("非法的暂存文件名。")
        return self.staging_dir(landmark_id) / file

    def _write_staged(self, landmark_id: int, staged_name: str, content: bytes):
        target = self.staging_dir(landmark_id) / staged_name
        target.write_bytes(content)
        return target

    def _staged_photo(self, landmark_id: int, kind: str, staged_name: str) -> StagedPhoto:
        meta = self._read_meta(landmark_id).get(staged_name) or {}
        return StagedPhoto(
            kind=str(meta.get("kind") or kind),
            file=staged_name,
            url=f"{STAGING_PUBLIC_PREFIX}/{landmark_id}/{staged_name}",
            alt=str(meta.get("alt") or self._default_alt(landmark_id)),
            caption=meta.get("caption"),
            credit=meta.get("credit"),
            license=str(meta.get("license") or _DEFAULT_LICENSE_BY_KIND.get(kind, "")),
            source_url=meta.get("source_url"),
        )

    # ---------- 暂存元数据持久化（刷新后授权/署名不丢） ----------

    def _meta_path(self, landmark_id: int):
        return self.staging_dir(landmark_id) / "_meta.json"

    def _read_meta(self, landmark_id: int) -> dict:
        path = self._meta_path(landmark_id)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_meta(self, landmark_id: int, meta: dict) -> None:
        path = self._meta_path(landmark_id)
        tmp = path.with_name("_meta.json.tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _update_meta(self, landmark_id: int, staged_name: str, fields: dict) -> None:
        meta = self._read_meta(landmark_id)
        entry = meta.get(staged_name) if isinstance(meta.get(staged_name), dict) else {}
        entry.update({key: value for key, value in fields.items() if value is not None})
        meta[staged_name] = entry
        self._write_meta(landmark_id, meta)

    def _drop_meta(self, landmark_id: int, staged_name: str) -> None:
        meta = self._read_meta(landmark_id)
        if staged_name in meta:
            del meta[staged_name]
            self._write_meta(landmark_id, meta)

    def _kind_of(self, staged_name: str) -> str:
        return "ai" if staged_name.startswith("ai-") else "upload"

    def _default_alt(self, landmark_id: int) -> str:
        landmark = self._get_landmark(landmark_id)
        return f"{landmark.name}实景" if landmark else "地标实景"

    # ---------- AI 找图与下载 ----------

    def ai_download(self, landmark_id: int) -> DownloadOutcome:
        landmark = self._get_landmark(landmark_id)
        if landmark is None:
            raise LandmarkAlbumNotFound("地标不存在。")
        queries = self._build_queries(landmark)
        providers = self._resolve_providers()
        notices: list[str] = []

        candidates: list = []
        seen: set[str] = set()
        for provider in providers:
            for query in queries:
                try:
                    result = provider.search(query, count=6)
                except Exception as exc:
                    notices.append(f"{getattr(provider, 'name', 'provider')} 检索失败：{exc}")
                    break
                for candidate in result.candidates:
                    if candidate.image_url not in seen:
                        seen.add(candidate.image_url)
                        candidates.append(candidate)
        candidates = candidates[:12]
        if not candidates and notices:
            raise AlbumEditorError("图片检索失败：" + "；".join(notices))

        candidates = self._rank_with_llm(landmark, candidates)
        failures: list[dict[str, str]] = []
        saved: list[StagedPhoto] = []
        for candidate in candidates:
            if len(saved) >= MAX_AI_DOWNLOADS:
                break
            try:
                content, content_type = self._download(candidate.image_url)
                photo = self.save_upload(landmark_id, candidate.image_url, content, content_type, kind="ai")
            except AlbumEditorError as exc:
                failures.append({"url": candidate.image_url, "reason": str(exc)})
                continue
            except Exception as exc:
                failures.append({"url": candidate.image_url, "reason": f"下载失败：{exc}"})
                continue
            staged = StagedPhoto(
                kind="ai",
                file=photo.file,
                url=photo.url,
                alt=f"{landmark.name}实景",
                caption=candidate.title[:120],
                credit=getattr(candidate, "artist", None) or None,
                license=getattr(candidate, "license", None) or _DEFAULT_LICENSE_BY_KIND["ai"],
                source_url=candidate.source_page_url or candidate.image_url,
            )
            saved.append(staged)
            self._update_meta(
                landmark_id,
                photo.file,
                {
                    "kind": "ai",
                    "alt": staged.alt,
                    "caption": staged.caption,
                    "credit": staged.credit,
                    "license": staged.license,
                    "source_url": staged.source_url,
                },
            )
        return DownloadOutcome(tuple(saved), tuple(failures), queries, tuple(notices))

    def _build_queries(self, landmark: Landmark) -> tuple[str, ...]:
        fallback = (landmark.name,)
        llm = self._llm
        if llm is None:
            llm = self._ensure_llm()
        work_title = landmark.ip_work.title if landmark.ip_work else ""
        location = landmark.location
        district = (location.district_name or "").strip() if location else ""
        city = (location.city_name or "").strip() if location else ""
        prompt = (
            "为 Wikimedia Commons（维基共享资源）生成图片搜索关键词。只输出 JSON：{\"queries\": [\"查询1\", ...]}。"
            f"地标：{landmark.name}；所属作品：{work_title or '未知'}；所在区县：{district or '未知'}；所在城市：{city or '未知'}。"
            "要求：1) 给 3-4 个短查询，每个 1-4 个词——Commons 全文检索是「与」语义，词多必空；"
            "2) 地标中文名原样作为一个查询（Commons 上大量中文文件名）；"
            "3) 给一个地名罗马化或英文查询（如 Yingxian Wooden Pagoda）；"
            "4) 仅当地标名有歧义时附加区县/城市限定词（区县优先于城市，例如「小西天 隰县」）；"
            "5) 禁止「实景/建筑/外观/取景地/photo」这类修饰词。"
        )
        try:
            payload = llm.generate_json(
                [{"role": "user", "content": prompt}],
            )
            queries = tuple(
                str(item).strip() for item in (payload.get("queries") or []) if str(item).strip()
            )[:4]
        except Exception:
            queries = ()
        return queries or fallback

    def _rank_with_llm(self, landmark: Landmark, candidates):
        llm = self._llm
        if llm is None:
            llm = self._ensure_llm()
        listing = [
            {"url": item.image_url, "title": item.title, "source": item.source_page_url}
            for item in candidates
        ]
        location = landmark.location
        district = (location.district_name or "").strip() if location else ""
        city = (location.city_name or "").strip() if location else ""
        work_title = landmark.ip_work.title if landmark.ip_work else ""
        where = "".join(filter(None, [district, city])) or "未知"
        prompt = (
            f"从候选图片中挑选与地标「{landmark.name}」最相关的最多 {MAX_AI_DOWNLOADS} 张。"
            f"背景：所属作品《{work_title or '未知'}》，位于{where}。"
            "请剔除明显属于同名但不同地的图片（例如北京北海公园的小西天殿，不是山西隰县小西天）。"
            "按相关性从高到低输出 URL，只输出 JSON：{\"selected\": [\"url1\", ...]}，"
            "只能使用候选列表中的 URL，不要新增。候选："
            + json.dumps(listing, ensure_ascii=False)
        )
        try:
            payload = llm.generate_json([{"role": "user", "content": prompt}])
            selected = [str(url) for url in (payload.get("selected") or [])]
            known = {item.image_url: item for item in candidates}
            ordered = [known[url] for url in selected if url in known]
            remaining = [item for item in candidates if item not in ordered]
            return ordered + remaining
        except Exception:
            return list(candidates)

    def _download(self, url: str) -> tuple[bytes, str]:
        if self._downloader is not None:
            return self._downloader(url)
        # trust_env 保持 True：本地网络可能依赖系统代理环境变量访问 Wikimedia
        last_error: Exception | None = None
        for attempt in range(2):  # 网络抖动（握手超时）时重试一次
            try:
                with httpx.Client(timeout=30.0, follow_redirects=True, trust_env=True) as client:
                    response = client.get(url, headers={"User-Agent": "WorldmarkAlbumEditor/1.0 (https://github.com/dragan2023/Worldmark; contact via repository issues)"})
                    response.raise_for_status()
                break
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == 1:
                    raise AlbumEditorError(f"图片下载失败：{exc}") from exc
        content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        return response.content, content_type

    def _resolve_providers(self) -> list:
        """解析图片来源：显式注入优先；默认 Commons（免 Key、自由授权、自带署名元数据）。

        博查当前未提供独立图片搜索端点（/v1/images/search 实测 404，2026-08），
        待其开放后再加入默认链路；web-search 仍用于一键入库的资料核实。
        """
        if self._image_provider is not None:
            return [self._image_provider]
        from app.integrations.images.wikimedia_commons import WikimediaCommonsImageProvider

        return [WikimediaCommonsImageProvider()]

    def _ensure_llm(self) -> DeepSeekClient:
        if self._llm is None:
            key = self._settings.deepseek_api_key
            if key and key.get_secret_value().strip():
                self._llm = DeepSeekClient(
                    key.get_secret_value().strip(),
                    base_url=self._settings.deepseek_base_url,
                    model=self._settings.deepseek_model,
                    thinking=self._settings.deepseek_thinking,
                )
        return self._llm

    # ---------- 编辑器快照与提交落库 ----------

    def editor_snapshot(self, landmark_id: int) -> dict:
        landmark = self._get_landmark(landmark_id)
        if landmark is None:
            raise LandmarkAlbumNotFound("地标不存在。")
        album_key = f"{landmark.ip_work.ip_type.value}:{landmark.name}"
        return {
            "landmark": {
                "id": landmark.id,
                "name": landmark.name,
                "ip_type": landmark.ip_work.ip_type.value,
                "work_title": landmark.ip_work.title if landmark.ip_work else "",
                "city": landmark.location.city_name if landmark.location else "",
            },
            "album_key": album_key,
            "published": self._published_entries(album_key),
            "staged": [photo.__dict__ | {"kind": photo.kind} for photo in self.list_staged(landmark_id)],
        }

    def _published_entries(self, album_key: str) -> list[dict]:
        manifest = self._read_manifest()
        entries = manifest.get("albums", {}).get(album_key, [])
        published = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            file = entry.get("file")
            if not isinstance(file, str) or not self._is_safe_relative_image(file):
                continue
            published.append(
                {
                    "kind": "published",
                    "file": file,
                    "url": f"{ALBUM_PUBLIC_PREFIX}/{file}",
                    "alt": str(entry.get("alt") or ""),
                    "caption": entry.get("caption"),
                    "credit": entry.get("credit"),
                    "license": entry.get("license") or "",
                    "source_url": entry.get("source_url"),
                }
            )
        return published

    def submit(self, landmark_id: int, photos: list[dict]) -> dict:
        """把编辑器工作集落库：移动文件、更新 manifest、清理被移除的旧图。"""
        landmark = self._get_landmark(landmark_id)
        if landmark is None:
            raise LandmarkAlbumNotFound("地标不存在。")
        if not photos:
            raise AlbumEditorError("工作集为空：至少保留一张图片，或先上传新图片。")

        album_key = f"{landmark.ip_work.ip_type.value}:{landmark.name}"
        current_entries = {entry["file"]: entry for entry in self._published_entries(album_key)}

        new_entries: list[dict] = []
        kept_published: set[str] = set()
        staged_moves: list[tuple[str, str]] = []

        for position, item in enumerate(photos, start=1):
            kind = item.get("kind")
            file = str(item.get("file") or "")
            alt = str(item.get("alt") or "").strip()
            if not alt:
                raise AlbumEditorError(f"第 {position} 张图片缺少图片说明（alt），请在放大预览中补填。")
            metadata = self._metadata(item)
            if kind == "published":
                if file not in current_entries:
                    raise AlbumEditorError(f"已发布图片不存在或路径非法：{file}")
                if file in kept_published:
                    raise AlbumEditorError(f"图片重复提交：{file}")
                kept_published.add(file)
                new_entries.append({"file": file, **metadata})
            elif kind in {"upload", "ai"}:
                source_path = self._resolve_staged_path(landmark_id, file)
                if not source_path.is_file():
                    raise StagingNotFoundError(f"暂存图片不存在：{file}")
                staged_moves.append((str(source_path), file))
                new_entries.append({"file": None, "alt": alt, **metadata, "_staged": file, "_kind": kind})
            else:
                raise AlbumEditorError(f"未知的图片来源类型：{kind}")

        images_dir = self._album_root / "images"
        target_dir = self._resolve_album_dir(images_dir, landmark, current_entries)
        target_dir.mkdir(parents=True, exist_ok=True)

        # 移动暂存文件并补全最终 file 路径
        final_entries: list[dict] = []
        for entry in new_entries:
            if entry.get("file") is not None:
                final_entries.append({k: v for k, v in entry.items()})
                continue
            staged_file = entry.pop("_staged")
            kind = entry.pop("_kind")
            extension = (staged_file.rsplit(".", 1)[-1] or "jpg").lower()
            final_name = f"{kind}-{uuid.uuid4().hex[:10]}.{extension}"
            (self.staging_dir(landmark_id) / staged_file).replace(target_dir / final_name)
            final_entries.append({**entry, "file": f"{landmark.ip_work.ip_type.value}/{target_dir.name}/{final_name}"})

        # 被移除的已发布照片移入回收站
        removed = 0
        trash_dir = self._album_root / TRASH_DIR_NAME
        for file in set(current_entries) - kept_published:
            trash_dir.mkdir(parents=True, exist_ok=True)
            source = images_dir / file
            if source.is_file():
                stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
                target = trash_dir / f"{stamp}-{file.replace('/', '_')}"
                source.replace(target)
            removed += 1

        self._write_album_entries(album_key, final_entries)
        meta_path = self._meta_path(landmark_id)
        if meta_path.exists():
            meta_path.unlink()
        return {
            "album_key": album_key,
            "published_count": len(final_entries),
            "added_count": len(staged_moves),
            "removed_count": removed,
        }

    @staticmethod
    def _metadata(item: dict) -> dict:
        def optional(value):
            text = str(value).strip() if value is not None else ""
            return text or None

        return {
            "alt": str(item.get("alt") or "").strip(),
            "caption": optional(item.get("caption")),
            "credit": optional(item.get("credit")),
            "license": str(item.get("license") or "").strip() or "未标注",
            "source_url": optional(item.get("source_url")),
        }

    def _resolve_album_dir(self, images_dir, landmark: Landmark, current_entries: dict) -> Path:
        for file in current_entries:
            parts = PurePosixPath(file).parts
            if len(parts) >= 2:
                return images_dir / landmark.ip_work.ip_type.value / parts[-2]
        return images_dir / landmark.ip_work.ip_type.value / f"landmark-{landmark.id}"

    # ---------- manifest 读写 ----------

    def _read_manifest(self) -> dict:
        path = self._album_root / "manifest.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {"schema_version": 1, "albums": {}}
        return raw if isinstance(raw, dict) else {"schema_version": 1, "albums": {}}

    def _write_album_entries(self, album_key: str, entries: list[dict]) -> None:
        manifest = self._read_manifest()
        albums = manifest.setdefault("albums", {})
        albums[album_key] = entries
        manifest["schema_version"] = manifest.get("schema_version", 1)
        path = self._album_root / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, path)

    # ---------- 内部工具 ----------

    def _get_landmark(self, landmark_id: int) -> Landmark | None:
        return self._db.scalar(
            select(Landmark)
            .options(selectinload(Landmark.ip_work), selectinload(Landmark.location))
            .where(Landmark.id == landmark_id)
        )
    @staticmethod
    def _is_safe_relative_image(file: str) -> bool:
        path = PurePosixPath(file)
        return (
            not path.is_absolute()
            and ".." not in path.parts
            and path.suffix.lower() in ALLOWED_EXTENSIONS
            and len(path.parts) >= 2
        )
