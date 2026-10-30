"""我的共创记录页：只展示当前登录用户自己的贡献与审核反馈。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, require_page_role
from app.db.session import get_db
from app.models.enums import UserRole
from app.services.contribution_records import list_user_contributions

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/contributions", response_class=HTMLResponse, include_in_schema=False)
def my_contributions_page(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    member: CurrentMember = Depends(require_page_role(UserRole.LEVEL2)),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """页面守卫保证已登录；查询复用与 API 相同的服务函数。"""
    assert member.user_id is not None
    result = list_user_contributions(db, member.user_id, page=page, page_size=page_size)
    return templates.TemplateResponse(
        request,
        "contributions/index.html",
        {
            "request": request,
            "title": "我的共创记录｜山河印迹",
            "result": result,
            "page": result["page"],
            "total_pages": result["total_pages"],
        },
    )
