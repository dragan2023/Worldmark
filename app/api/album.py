"""地标相册编辑 API：编辑器快照、批量上传、AI 找图、删除暂存、提交落库。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, require_member
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.services.landmark_album_editor import (
    MAX_UPLOAD_BYTES,
    AlbumConflictError,
    AlbumEditorError,
    LandmarkAlbumEditorService,
    LandmarkAlbumNotFound,
    StagingNotFoundError,
)
from app.services.key_resolution import KeyResolutionService
from app.services.landmark_access import LandmarkAccessError, get_landmark_for_edit
from app.services.review import LandmarkReviewService
from app.models.user import User

router = APIRouter(prefix="/api/v1/landmarks", tags=["album-editor"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_BATCH_UPLOADS = 12


class AlbumSubmitPhoto(BaseModel):
    kind: str = Field(pattern="^(published|upload|ai)$")
    file: str = Field(min_length=1, max_length=300)
    alt: str = Field(min_length=1, max_length=300)
    caption: str | None = Field(default=None, max_length=500)
    credit: str | None = Field(default=None, max_length=200)
    license: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=1000)


class AlbumSubmitRequest(BaseModel):
    photos: list[AlbumSubmitPhoto] = Field(min_length=1, max_length=60)
    # 编辑器快照返回的 revision；提供时必须与当前相册一致，否则 409。
    expected_revision: str | None = Field(default=None, max_length=64)


UPLOAD_CHUNK_BYTES = 64 * 1024


async def _read_upload_limited(file: UploadFile) -> bytes:
    """分块读取，超过上限立即停止，不把超大文件整体读进内存。"""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise AlbumEditorError("单张图片不能超过 8MB。")
        chunks.append(chunk)
    return b"".join(chunks)


def get_album_storage_root() -> Path:
    """相册文件根目录：生产是项目根，测试通过 dependency_overrides 指向隔离目录。

    没有这层依赖时，测试会读到真实的 data/contributions/landmark_albums/manifest.json，
    真实数据一旦变化（例如正式键迁移成 landmark:<id>），同 id 的合成地标就会串入真实图片。
    """
    return PROJECT_ROOT


def get_album_editor(
    member: CurrentMember = Depends(require_member),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    storage_root: Path = Depends(get_album_storage_root),
) -> LandmarkAlbumEditorService:
    """装配编辑器服务（密钥按用户隔离）；测试通过 dependency_overrides 注入替身。"""
    effective = KeyResolutionService(db).effective_settings(member, settings)
    return LandmarkAlbumEditorService(db, storage_root, settings=effective)


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _guard_edit(db: Session, member: CurrentMember, landmark_id: int) -> bool:
    """贡献者或管理员可编辑；返回是否管理员（管理员修改即时生效）。"""
    try:
        _, is_admin = get_landmark_for_edit(db, member, landmark_id)
    except LandmarkAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return is_admin


def _trigger_rereview(db: Session, member: CurrentMember, landmark_id: int) -> None:
    """贡献者修改相册后进入重新审核：只撤回该地标，不影响同作品其他条目。"""
    user = db.get(User, member.user_id) if member.user_id else None
    actor = user.username if user is not None else f"user:{member.user_id}"
    LandmarkReviewService(db).request_rereview(
        landmark_id, actor=actor, reason="贡献者更新地标相册，进入重新审核。"
    )


@router.get("/{landmark_id}/album/editor")
def editor_snapshot(
    landmark_id: int,
    member: CurrentMember = Depends(require_member),
    editor: LandmarkAlbumEditorService = Depends(get_album_editor),
    db: Session = Depends(get_db),
) -> dict:
    _guard_edit(db, member, landmark_id)
    try:
        return editor.editor_snapshot(landmark_id)
    except LandmarkAlbumNotFound as exc:
        raise _not_found(exc) from exc


@router.post("/{landmark_id}/album/editor/uploads")
async def upload_photos(
    landmark_id: int,
    files: list[UploadFile] = File(...),
    member: CurrentMember = Depends(require_member),
    editor: LandmarkAlbumEditorService = Depends(get_album_editor),
    db: Session = Depends(get_db),
) -> dict:
    _guard_edit(db, member, landmark_id)
    if len(files) > MAX_BATCH_UPLOADS:
        raise HTTPException(status_code=413, detail=f"单次最多上传 {MAX_BATCH_UPLOADS} 张图片。")
    saved: list[dict] = []
    errors: list[dict[str, str]] = []
    for file in files:
        try:
            content = await _read_upload_limited(file)
            photo = editor.save_upload(landmark_id, file.filename or "", content, file.content_type)
        except AlbumEditorError as exc:
            errors.append({"file": file.filename or "未命名", "reason": str(exc)})
            continue
        saved.append(photo.__dict__)
    if not saved and errors:
        raise HTTPException(status_code=422, detail=errors[0]["reason"])
    return {"saved": saved, "errors": errors, "staged": [photo.__dict__ for photo in editor.list_staged(landmark_id)]}


@router.post("/{landmark_id}/album/editor/ai-download")
def ai_download(
    landmark_id: int,
    member: CurrentMember = Depends(require_member),
    editor: LandmarkAlbumEditorService = Depends(get_album_editor),
    db: Session = Depends(get_db),
) -> dict:
    _guard_edit(db, member, landmark_id)
    try:
        outcome = editor.ai_download(landmark_id)
    except (LandmarkAlbumNotFound, StagingNotFoundError) as exc:
        raise _not_found(exc) from exc
    except AlbumEditorError as exc:
        status_code = 503 if "未配置" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return {
        "saved": [photo.__dict__ for photo in outcome.saved],
        "failures": [dict(item) for item in outcome.failures],
        "queries": list(outcome.queries),
        "notices": list(outcome.notices),
        "staged": [photo.__dict__ for photo in editor.list_staged(landmark_id)],
    }


@router.delete("/{landmark_id}/album/editor/staged/{filename}")
def delete_staged(
    landmark_id: int,
    filename: str,
    member: CurrentMember = Depends(require_member),
    editor: LandmarkAlbumEditorService = Depends(get_album_editor),
    db: Session = Depends(get_db),
) -> dict:
    _guard_edit(db, member, landmark_id)
    try:
        editor.delete_staged(landmark_id, filename)
    except StagingNotFoundError as exc:
        raise _not_found(exc) from exc
    except AlbumEditorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"deleted": filename, "staged": [photo.__dict__ for photo in editor.list_staged(landmark_id)]}


@router.post("/{landmark_id}/album/submit")
def submit_album(
    landmark_id: int,
    payload: AlbumSubmitRequest,
    member: CurrentMember = Depends(require_member),
    editor: LandmarkAlbumEditorService = Depends(get_album_editor),
    db: Session = Depends(get_db),
) -> dict:
    is_admin = _guard_edit(db, member, landmark_id)
    try:
        result = editor.submit(
            landmark_id,
            [item.model_dump() for item in payload.photos],
            expected_revision=payload.expected_revision,
        )
    except (LandmarkAlbumNotFound, StagingNotFoundError) as exc:
        raise _not_found(exc) from exc
    except AlbumConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AlbumEditorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not is_admin:
        _trigger_rereview(db, member, landmark_id)
        result["review_note"] = "相册已更新并进入重新审核，重新审核通过前该地标将暂时下架。"
    return result
