from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"title": "登录｜山河印迹"})


@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "register.html", {"title": "注册｜山河印迹"})


@router.get("/account/api-keys", response_class=HTMLResponse, include_in_schema=False)
def account_keys_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "account_api_keys.html", {"title": "个人密钥｜山河印迹"})
