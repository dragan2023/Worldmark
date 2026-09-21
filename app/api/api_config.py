"""API 配置页接口：状态快照、本地密钥保存与连通性验证。

写入口仅在本地/开发环境开放（APP_ENV=production 拒绝），并做同源校验，
防止其他网页跨站调用本机接口改写 .env。
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.auth import require_admin

from app.core.config import Settings, get_settings
from app.services.api_config_service import (
    WRITABLE_ENV_NAMES,
    build_snapshot,
    refresh_runtime_settings,
    run_client_probe,
    update_env_file,
)

router = APIRouter(prefix="/api/v1/api-config", tags=["api-config"], dependencies=[Depends(require_admin)])


class ApiConfigUpdateRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class ApiConfigVerifyRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=50)


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    try:
        return urlparse(origin).netloc == request.url.netloc
    except ValueError:
        return False


@router.get("")
def get_api_config(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """返回各内置客户端的配置状态快照（密钥仅掩码展示）。"""
    return build_snapshot(settings)


@router.put("")
def update_api_config(
    payload: ApiConfigUpdateRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if settings.is_production:
        raise HTTPException(status_code=403, detail="生产环境请通过系统环境变量配置密钥，网页写入已被禁用。")
    if not _same_origin(request):
        raise HTTPException(status_code=403, detail="跨站请求被拒绝。")
    values = {key.strip(): value for key, value in payload.values.items()}
    unknown = sorted(set(values) - WRITABLE_ENV_NAMES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"不支持写入的环境变量：{', '.join(unknown)}")
    try:
        env_path = update_env_file(values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    refresh_runtime_settings()
    refreshed = get_settings()
    return {"env_file": str(env_path), "written": sorted(values), "config": build_snapshot(refreshed)}


@router.post("/verify")
def verify_api_config(
    payload: ApiConfigVerifyRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        ok, message = run_client_probe(payload.client_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"client_id": payload.client_id, "ok": ok, "message": message}
