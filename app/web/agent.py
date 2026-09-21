from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/intake", response_class=HTMLResponse, include_in_schema=False)
def intake_page(request: Request) -> HTMLResponse:
    """「一键入库」页面：自然语言输入，AI 生成候选地标条目。"""
    return templates.TemplateResponse(request, "agent_intake.html", {"title": "一键入库｜山河印迹"})
