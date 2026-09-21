"""一键入库 API：登录门槛、错误映射与成功响应。"""

import pytest

from app.api.agent import get_intake_agent
from app.core.auth import create_access_token
from app.models.enums import MembershipTier
from app.services.landmark_intake_agent import (
    IntakeOutcome,
    IntakeStep,
    LandmarkIntakeDuplicate,
    LandmarkIntakeError,
    LandmarkIntakeUnavailable,
)


class StubAgent:
    def __init__(self, outcome=None, error=None):
        self._outcome = outcome
        self._error = error
        self.received = None

    def intake(self, text):
        self.received = text
        if self._error is not None:
            raise self._error
        return self._outcome


def _outcome():
    return IntakeOutcome(
        landmark_id=7,
        work_title="黑神话：悟空",
        ip_type="game",
        landmark_name="小西天",
        address="山西省临汾市隰县凤山小西天",
        latitude=36.0667,
        longitude=110.9389,
        description="第一段。\n第二段。\n第三段。",
        source_url="https://news.example/xiaoxitian",
        warnings=["来源未经联网核实"],
        steps=[IntakeStep("parse", "ok", "黑神话：悟空 × 小西天")],
        search_run_id=None,
    )


def _auth_headers(db_session):
    from tests.factories import create_member

    member = create_member(db_session, MembershipTier.FREE)
    return {"Authorization": f"Bearer {create_access_token(member.id)}"}


def test_intake_requires_login(client):
    response = client.post("/api/v1/agent/landmarks/intake", json={"input": "黑神话悟空 小西天"})
    assert response.status_code == 401


def test_intake_success_returns_entry_summary(client, app, db_session):
    stub = StubAgent(outcome=_outcome())
    app.dependency_overrides[get_intake_agent] = lambda: stub

    response = client.post(
        "/api/v1/agent/landmarks/intake",
        json={"input": "黑神话悟空 小西天"},
        headers=_auth_headers(db_session),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["landmark_id"] == 7
    assert data["detail_url"] == "/landmarks/7"
    assert data["work_title"] == "黑神话：悟空"
    assert data["latitude"] == pytest.approx(36.0667)
    assert data["warnings"] == ["来源未经联网核实"]
    assert data["steps"][0]["name"] == "parse"
    assert "审核" in data["review_note"]
    assert stub.received == "黑神话悟空 小西天"


def test_intake_maps_unavailable_to_503(client, app, db_session):
    app.dependency_overrides[get_intake_agent] = lambda: StubAgent(
        error=LandmarkIntakeUnavailable("未配置 LLM API Key")
    )
    response = client.post(
        "/api/v1/agent/landmarks/intake",
        json={"input": "黑神话悟空 小西天"},
        headers=_auth_headers(db_session),
    )
    assert response.status_code == 503
    assert "LLM" in response.json()["detail"]


def test_intake_maps_duplicate_to_409(client, app, db_session):
    app.dependency_overrides[get_intake_agent] = lambda: StubAgent(
        error=LandmarkIntakeDuplicate("已存在相同条目")
    )
    response = client.post(
        "/api/v1/agent/landmarks/intake",
        json={"input": "黑神话悟空 小西天"},
        headers=_auth_headers(db_session),
    )
    assert response.status_code == 409


def test_intake_maps_validation_error_to_422(client, app, db_session):
    app.dependency_overrides[get_intake_agent] = lambda: StubAgent(
        error=LandmarkIntakeError("无法识别作品类型")
    )
    response = client.post(
        "/api/v1/agent/landmarks/intake",
        json={"input": "听不懂的输入"},
        headers=_auth_headers(db_session),
    )
    assert response.status_code == 422


def test_intake_rejects_blank_and_oversized_input(client, db_session):
    headers = _auth_headers(db_session)
    assert client.post("/api/v1/agent/landmarks/intake", json={"input": "字"}, headers=headers).status_code == 422
    assert client.post("/api/v1/agent/landmarks/intake", json={"input": "字" * 501}, headers=headers).status_code == 422


def test_intake_page_renders(client):
    response = client.get("/intake")
    assert response.status_code == 200
    assert "一键入库" in response.text
    assert "AI 分析并入库" in response.text


def test_intake_records_contribution_ownership(client, app, db_session):
    """入库成功即写入贡献归属（发布后用于自动提权）。"""
    from app.models.contribution import LandmarkContribution
    from app.models.user import User
    from tests.factories import create_member

    member = create_member(db_session, MembershipTier.FREE)
    db_session.commit()
    app.dependency_overrides[get_intake_agent] = lambda: StubAgent(outcome=_outcome())
    response = client.post(
        "/api/v1/agent/landmarks/intake",
        json={"input": "黑神话悟空 小西天"},
        headers={"Authorization": f"Bearer {create_access_token(member.id)}"},
    )
    assert response.status_code == 200

    contribution = db_session.query(LandmarkContribution).filter_by(landmark_id=7).one()
    assert contribution.contributor_user_id == member.id
    user = db_session.get(User, member.id)
    assert contribution.contributor_name == user.username
