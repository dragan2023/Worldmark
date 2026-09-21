"""「一键入库」AI Agent 接口。

权限口径：需要登录会员（开发环境 dev_bypass_auth 自动以本地开发者身份运行）。
生成结果固定为 candidate 候选状态，公开仍走管理员审核发布流程。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, require_member
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.contribution import LandmarkContribution
from app.models.user import User
from app.services.landmark_intake_agent import (
    LandmarkIntakeAgent,
    LandmarkIntakeDuplicate,
    LandmarkIntakeError,
    LandmarkIntakeUnavailable,
)
from app.services.key_resolution import KeyResolutionService

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class LandmarkIntakeRequest(BaseModel):
    """自然语言输入：作品名 + 地标名。"""

    input: str = Field(min_length=2, max_length=500, examples=["黑神话悟空 小西天"])


def get_intake_agent(
    member: CurrentMember = Depends(require_member),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LandmarkIntakeAgent:
    """装配默认 Agent（密钥按用户隔离）；测试通过 dependency_overrides 注入替身。"""
    effective = KeyResolutionService(db).effective_settings(member, settings)
    return LandmarkIntakeAgent(db, effective)


@router.post("/landmarks/intake")
def intake_landmark(
    payload: LandmarkIntakeRequest,
    member: CurrentMember = Depends(require_member),
    agent: LandmarkIntakeAgent = Depends(get_intake_agent),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        outcome = agent.intake(payload.input)
    except LandmarkIntakeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LandmarkIntakeDuplicate as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LandmarkIntakeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 记录贡献归属：发布后用于自动提权（二级 → 一级）
    contributor = db.get(User, member.user_id)
    if contributor is not None and contributor.username:
        contributor_name = contributor.username
    elif contributor is not None and contributor.email:
        contributor_name = contributor.email.split("@")[0]
    else:
        contributor_name = f"会员{member.user_id}"
    db.add(LandmarkContribution(
        landmark_id=outcome.landmark_id,
        contributor_name=contributor_name[:100],
        contributor_user_id=member.user_id,
    ))
    db.commit()

    return {
        "landmark_id": outcome.landmark_id,
        "detail_url": f"/landmarks/{outcome.landmark_id}",
        "work_title": outcome.work_title,
        "ip_type": outcome.ip_type,
        "landmark_name": outcome.landmark_name,
        "address": outcome.address,
        "latitude": outcome.latitude,
        "longitude": outcome.longitude,
        "description": outcome.description,
        "source_url": outcome.source_url,
        "warnings": outcome.warnings,
        "steps": [{"name": step.name, "status": step.status, "detail": step.detail} for step in outcome.steps],
        "search_run_id": outcome.search_run_id,
        "review_note": "条目已作为候选入库（未公开），需管理员审核发布后才会出现在目录中。",
    }
