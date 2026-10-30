from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import CurrentMember, require_page_role
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.landmark import Landmark
from app.services.landmark_access import LandmarkAccessError, get_landmark_for_edit

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/landmarks/{landmark_id}/album/edit", response_class=HTMLResponse, include_in_schema=False)
def album_edit_page(
    landmark_id: int,
    request: Request,
    member: CurrentMember = Depends(require_page_role(UserRole.LEVEL2)),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """地标相册编辑页：多图上传 / AI 找图 / 灯箱预览与元数据编辑 / 提交落库。

    页面级先判权限：匿名跳登录，非贡献者/管理员返回说明性 403，避免展示伪可用编辑器。
    """
    try:
        get_landmark_for_edit(db, member, landmark_id)
    except LandmarkAccessError as exc:
        status_code = 404 if "不存在" in str(exc) else 403
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    landmark = db.scalar(
        select(Landmark).options(selectinload(Landmark.ip_work)).where(Landmark.id == landmark_id)
    )
    if landmark is None:
        raise HTTPException(status_code=404, detail="地标不存在。")
    return templates.TemplateResponse(
        request,
        "album_edit.html",
        {
            "title": f"编辑地标：{landmark.name}｜山河印迹",
            "landmark_id": landmark.id,
            "landmark_name": landmark.name,
            "work_title": landmark.ip_work.title if landmark.ip_work else "",
        },
    )
