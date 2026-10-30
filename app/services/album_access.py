"""相册图片访问判定：公开目录、编辑预览、未发布归属。

对外只暴露一个判断入口，页面与图片路由共用同一套「谁能看这张图」规则：

- 正式相册图片：只有所属地标当前公开（或请求者是该地标贡献者/管理员）才能读；
  待审/已撤回地标的历史 URL 因此不能绕过内容审核。
- 暂存图片：仅该地标的贡献者或管理员可读，且只允许该地标暂存目录下的白名单文件。

反向索引按 manifest 的 mtime 缓存，提交后自动失效。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import IPType, PublicationStatus, VerificationStatus
from app.models.ip_work import IPWork
from app.models.landmark import Landmark
from app.services.landmark_albums import (
    ALLOWED_EXTENSIONS,
    ALBUM_ROOT,
    LandmarkAlbumService,
    album_key,
)
from app.services.landmark_access import LandmarkAccessError, get_landmark_for_edit

logger = logging.getLogger("app.albums")

_index_lock = Lock()
_index_cache: dict[tuple[str, int, int], dict[str, tuple[str, ...]]] = {}


@dataclass(frozen=True)
class AlbumImageDecision:
    allowed: bool
    reason: str = ""


def album_images_root(project_root: Path) -> Path:
    return (project_root / ALBUM_ROOT / "images").resolve()


def resolve_album_image(project_root: Path, file_path: str) -> Path | None:
    """把请求路径解析为 images 目录内的真实文件；越界或后缀不符返回 None。"""
    relative = PurePosixPath(file_path)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    if relative.suffix.lower() not in ALLOWED_EXTENSIONS:
        return None
    root = album_images_root(project_root)
    candidate = (root / Path(*relative.parts)).resolve()
    if root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def reverse_index(project_root: Path) -> dict[str, tuple[str, ...]]:
    """manifest 文件路径 → 引用它的相册键列表。"""
    service = LandmarkAlbumService(project_root)
    manifest_path = project_root / ALBUM_ROOT / "manifest.json"
    try:
        stat = manifest_path.stat()
    except FileNotFoundError:
        return {}
    cache_key = (str(manifest_path), stat.st_mtime_ns, stat.st_size)
    with _index_lock:
        cached = _index_cache.get(cache_key)
    if cached is not None:
        return cached

    index: dict[str, set[str]] = {}
    for key in service.album_keys():
        for entry in service.entries_for_key(key):
            file = entry.get("file")
            if isinstance(file, str):
                index.setdefault(file, set()).add(key)
    result = {file: tuple(sorted(keys)) for file, keys in index.items()}
    with _index_lock:
        _index_cache.clear()
        _index_cache[cache_key] = result
    return result


def landmark_is_public(session: Session, landmark_id: int) -> bool:
    row = session.execute(
        select(Landmark.id)
        .join(IPWork, Landmark.ip_work_id == IPWork.id)
        .where(
            Landmark.id == landmark_id,
            Landmark.deleted_at.is_(None),
            Landmark.verification_status == VerificationStatus.VERIFIED,
            Landmark.published_at.is_not(None),
            IPWork.status == PublicationStatus.PUBLISHED,
        )
    ).first()
    return row is not None


def _landmark_id_for_legacy_key(session: Session, key: str) -> int | None:
    """旧键 ``<ip_type>:<名称>`` → 地标 id；同名多义时返回 None（不猜归属）。"""
    ip_type_value, _, name = key.partition(":")
    try:
        ip_type = IPType(ip_type_value)
    except ValueError:
        return None
    ids = session.scalars(
        select(Landmark.id)
        .join(IPWork, Landmark.ip_work_id == IPWork.id)
        .where(Landmark.name == name, IPWork.ip_type == ip_type)
    ).all()
    if len(ids) == 1:
        return ids[0]
    if len(ids) > 1:
        logger.warning("album key %s matches %d landmarks; access left permissive until migration", key, len(ids))
    return None


def can_read_published_image(
    session: Session,
    project_root: Path,
    file_path: str,
    member,
) -> AlbumImageDecision:
    """正式相册图片访问判定。"""
    keys = reverse_index(project_root).get(file_path)
    if not keys:
        # 未被任何相册条目引用：不对外发布（含 _trash、临时文件、手工散图）
        return AlbumImageDecision(False, "未被相册引用")

    for key in keys:
        if key.startswith("landmark:"):
            landmark_id = int(key.split(":", 1)[1])
        else:
            landmark_id = _landmark_id_for_legacy_key(session, key)
            if landmark_id is None:
                # 历史键多义或无法映射：迁移完成前保持可读，避免误伤用户图片
                return AlbumImageDecision(True, "历史键暂无法唯一映射")
        if landmark_is_public(session, landmark_id):
            return AlbumImageDecision(True)
        if member is not None and member.user_id is not None:
            try:
                get_landmark_for_edit(session, member, landmark_id)
            except LandmarkAccessError:
                continue
            return AlbumImageDecision(True, "编辑者预览")
    return AlbumImageDecision(False, "所属地标未公开")


def can_read_staged_image(
    session: Session,
    landmark_id: int,
    filename: str,
    member,
) -> AlbumImageDecision:
    """暂存图片访问判定：必须是该地标的贡献者或管理员。"""
    if member is None or member.user_id is None:
        return AlbumImageDecision(False, "需要登录")
    relative = PurePosixPath(filename)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() not in ALLOWED_EXTENSIONS:
        return AlbumImageDecision(False, "非法文件名")
    try:
        get_landmark_for_edit(session, member, landmark_id)
    except LandmarkAccessError as exc:
        return AlbumImageDecision(False, str(exc))
    return AlbumImageDecision(True)
