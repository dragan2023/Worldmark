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
    AlbumEditorError,
    LandmarkAlbumEditorService,
    LandmarkAlbumNotFound,
    StagingNotFoundError,
)
from app.services.key_resolution import KeyResolutionService
from app.services.landmark_access import LandmarkAccessError, get_landmark_for_edit
from app.models.enums import PublicationStatus, VerificationStatus

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


def get_album_editor(
    member: CurrentMember = Depends(require_member),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LandmarkAlbumEditorService:
    """装配编辑器服务（密钥按用户隔离）；测试通过 dependency_overrides 注入替身。"""
    effective = KeyResolutionService(db).effective_settings(member, settings)
    return LandmarkAlbumEditorService(db, PROJECT_ROOT, settings=effective)


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _guard_edit(db: Session, member: CurrentMember, landmark_id: int) -> bool:
    """贡献者或管理员可编辑；返回是否管理员（管理员修改即时生效）。"""
    try:
        _, is_admin = get_landmark_for_edit(db, member, landmark_id)
    except LandmarkAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return is_admin


def _trigger_rereview(db: Session, landmark_id: int) -> None:
    """贡献者修改后进入重新审核：撤回上架、回到待审核。"""
    from app.models.landmark import Landmark

    landmark = db.get(Landmark, landmark_id)
    if landmark is None:
        return
    landmark.verification_status = VerificationStatus.CANDIDATE
    landmark.published_at = None
    landmark.ip_work.status = PublicationStatus.DRAFT
    db.commit()


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
        content = await file.read()
        try:
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
        result = editor.submit(landmark_id, [item.model_dump() for item in payload.photos])
    except (LandmarkAlbumNotFound, StagingNotFoundError) as exc:
        raise _not_found(exc) from exc
    except AlbumEditorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not is_admin:
        _trigger_rereview(db, landmark_id)
        result["review_note"] = "相册已更新并进入重新审核，重新审核通过前该地标将暂时下架。"
    return result
