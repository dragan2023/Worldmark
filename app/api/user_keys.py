"""个人密钥管理：用户自配第三方服务密钥（永不回传明文）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, require_member
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user_api_key import UserApiKey
from app.services.api_config_service import run_client_probe
from app.services.key_resolution import PROVIDER_FIELDS, KeyResolutionService

router = APIRouter(prefix="/api/v1/me/api-keys", tags=["me"])

# provider → （展示名，探针 client_id，申请地址，填写提示）
_PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "deepseek": {
        "label": "DeepSeek（LLM 大模型）",
        "probe": "llm",
        "apply_url": "https://platform.deepseek.com/api_keys",
        "hint": "sk- 开头；用于一键入库与 AI 找图的智能检索",
    },
    "amap": {
        "label": "高德 Web 服务 Key",
        "probe": "amap",
        "apply_url": "https://console.amap.com/dev/key/app",
        "hint": "32 位字符串；用于地理编码与行程路线",
    },
    "bocha": {
        "label": "博查 AI 搜索",
        "probe": "bocha",
        "apply_url": "https://open.bochaai.com/api-keys",
        "hint": "sk- 开头；用于一键入库的联网核实（可选）",
    },
    "meituan": {
        "label": "美团酒旅官方 Skill",
        "probe": "meituan",
        "apply_url": "https://developer.meituan.com/zh/v2/dev/token",
        "hint": "美团开放平台 Token；用于行程中的酒旅数据（可选）",
    },
}


class ApiKeyUpsert(BaseModel):
    value: str = Field(min_length=4, max_length=256)
    verify: bool = True


def _require_provider(provider: str) -> None:
    if provider not in PROVIDER_FIELDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"未知的密钥类型：{provider}")


@router.get("")
def list_my_keys(member: CurrentMember = Depends(require_member), db: Session = Depends(get_db)) -> dict[str, object]:
    rows = db.scalars(select(UserApiKey).where(UserApiKey.user_id == member.user_id)).all()
    by_provider = {row.provider: row for row in rows}
    catalog = [
        {
            "provider": provider,
            "label": spec["label"],
            "apply_url": spec["apply_url"],
            "hint": spec["hint"],
            "configured": provider in by_provider,
            "key_hint": by_provider[provider].key_hint if provider in by_provider else None,
            "is_active": by_provider[provider].is_active if provider in by_provider else None,
            "verified_at": (
                by_provider[provider].verified_at.isoformat() if provider in by_provider and by_provider[provider].verified_at else None
            ),
        }
        for provider, spec in _PROVIDER_CATALOG.items()
    ]
    return {"items": catalog}


@router.put("/{provider}")
def upsert_my_key(
    provider: str,
    payload: ApiKeyUpsert,
    member: CurrentMember = Depends(require_member),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_provider(provider)
    raw = payload.value.strip()
    if not raw:
        raise HTTPException(status_code=422, detail="密钥内容不能为空。")

    verified_at = None
    if payload.verify:
        fields = PROVIDER_FIELDS[provider]
        probe_settings = get_settings().model_copy(
            update={field: SecretStr(raw) for field in fields}
        )
        ok, message = run_client_probe(_PROVIDER_CATALOG[provider]["probe"], probe_settings)
        if not ok:
            raise HTTPException(status_code=422, detail=f"密钥验证未通过：{message}")
        verified_at = datetime.now(UTC)

    row = KeyResolutionService(db).set_key(member.user_id, provider, raw, verified=verified_at is not None)
    return {
        "provider": provider,
        "key_hint": row.key_hint,
        "is_active": row.is_active,
        "verified": verified_at is not None,
    }


@router.delete("/{provider}")
def delete_my_key(
    provider: str,
    member: CurrentMember = Depends(require_member),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_provider(provider)
    deleted = KeyResolutionService(db).delete_key(member.user_id, provider)
    return {"provider": provider, "deleted": deleted}


@router.post("/{provider}/verify")
def verify_my_key(
    provider: str,
    member: CurrentMember = Depends(require_member),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_provider(provider)
    raw = KeyResolutionService(db).user_key(member.user_id, provider)
    if raw is None:
        raise HTTPException(status_code=404, detail="尚未配置该密钥。")
    fields = PROVIDER_FIELDS[provider]
    probe_settings = get_settings().model_copy(
        update={field: SecretStr(raw) for field in fields}
    )
    ok, message = run_client_probe(_PROVIDER_CATALOG[provider]["probe"], probe_settings)
    row = db.scalar(
        select(UserApiKey).where(UserApiKey.user_id == member.user_id, UserApiKey.provider == provider)
    )
    if row is not None:
        row.verified_at = datetime.now(UTC) if ok else None
        db.commit()
    return {"provider": provider, "ok": ok, "message": message}
