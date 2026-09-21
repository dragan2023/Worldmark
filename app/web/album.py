from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.landmark import Landmark

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/landmarks/{landmark_id}/album/edit", response_class=HTMLResponse, include_in_schema=False)
def album_edit_page(landmark_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """地标相册编辑页：多图上传 / AI 找图 / 灯箱预览与元数据编辑 / 提交落库。"""
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
