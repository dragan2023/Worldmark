from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/intake", response_class=HTMLResponse, include_in_schema=False)
def intake_page(request: Request) -> HTMLResponse:
    """「参与共创」页面：自然语言输入，AI 生成候选地标条目（提交后进入审核）。"""
    return templates.TemplateResponse(request, "agent_intake.html", {"title": "参与共创｜山河印迹"})
