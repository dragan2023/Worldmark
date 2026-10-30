"""相册图片访问路由：替代原先对整个目录的匿名静态挂载。

- 正式图片：只服务「所属地标当前公开」或「请求者是该地标贡献者/管理员」的文件；
- 暂存图片：必须登录且是该地标的贡献者/管理员，禁止 _meta.json 与其他用户目录。

响应统一 ``Cache-Control: private, no-store``，不返回磁盘路径。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, get_current_member
from app.db.session import get_db
from app.services.album_access import (
    can_read_published_image,
    can_read_staged_image,
    resolve_album_image,
)
from app.services.landmark_album_editor import STAGING_ROOT

router = APIRouter(include_in_schema=False)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


def get_project_root() -> Path:
    """项目根目录依赖；测试通过 dependency_overrides 指向隔离目录。"""
    return PROJECT_ROOT


@router.get("/contributions/landmark-albums/images/{file_path:path}")
def published_album_image(
    file_path: str,
    member: CurrentMember = Depends(get_current_member),
    db: Session = Depends(get_db),
    project_root: Path = Depends(get_project_root),
) -> FileResponse:
    resolved = resolve_album_image(project_root, file_path)
    if resolved is None:
        raise HTTPException(status_code=404, detail="图片不存在。")
    decision = can_read_published_image(db, project_root, file_path, member)
    if not decision.allowed:
        raise HTTPException(status_code=404, detail="图片不存在。")
    return FileResponse(resolved, headers=PRIVATE_HEADERS)


@router.get("/staging/landmark-albums/{landmark_id}/{filename}")
def staged_album_image(
    landmark_id: int,
    filename: str,
    member: CurrentMember = Depends(get_current_member),
    db: Session = Depends(get_db),
    project_root: Path = Depends(get_project_root),
) -> FileResponse:
    decision = can_read_staged_image(db, landmark_id, filename, member)
    if not decision.allowed:
        # 未登录与无权限都按「不存在」处理，避免暴露暂存区结构
        raise HTTPException(status_code=404, detail="图片不存在。")
    staging_root = (project_root / STAGING_ROOT / str(landmark_id)).resolve()
    candidate = (staging_root / filename).resolve()
    if staging_root not in candidate.parents or not candidate.is_file():
        raise HTTPException(status_code=404, detail="图片不存在。")
    return FileResponse(candidate, headers=PRIVATE_HEADERS)
