from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/contribute", response_class=HTMLResponse, include_in_schema=False)
def contribution_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "contributions/new.html", {"title": "提交共创地标｜IP 地标旅游"})
