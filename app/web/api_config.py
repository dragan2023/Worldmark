from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.auth import get_current_member

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/settings/api", response_class=HTMLResponse, include_in_schema=False, response_model=None)
def api_config_page(
    request: Request,
    member=Depends(get_current_member),
) -> HTMLResponse | RedirectResponse:
    """系统密钥配置页仅管理员可见；普通用户引导到个人密钥页。"""
    if member.user_id is None:
        return RedirectResponse("/login?next=/settings/api", status_code=302)
    if member.role != "admin":
        return RedirectResponse("/account/api-keys", status_code=302)
    return templates.TemplateResponse(request, "api_config.html", {"title": "API 配置｜山河印迹"})
