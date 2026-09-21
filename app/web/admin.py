from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import get_current_member

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False, response_model=None)
def admin_dashboard_page(
    request: Request,
    member=Depends(get_current_member),
) -> HTMLResponse | RedirectResponse:
    """管理后台（仅管理员）：用户管理 + 地标审核。"""
    if member.user_id is None:
        return RedirectResponse("/login?next=/admin", status_code=302)
    if member.role != "admin":
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "admin_dashboard.html", {"title": "管理后台｜山河印迹"})


@router.get("/admin/users", response_class=HTMLResponse, include_in_schema=False, response_model=None)
def admin_users_page(
    request: Request,
    member=Depends(get_current_member),
) -> HTMLResponse | RedirectResponse:
    """旧地址：并入管理后台用户标签页。"""
    if member.user_id is None:
        return RedirectResponse("/login?next=/admin", status_code=302)
    return RedirectResponse("/admin", status_code=302)
