"""M6：登录限速（内存级滑动窗口）。"""

from app.core import rate_limit
from app.models.enums import MembershipTier


def setup_function(_) -> None:
    rate_limit._failures.clear()


def test_blocks_after_max_failures():
    for _ in range(rate_limit._MAX_FAILURES):
        assert rate_limit.register_failure("1.2.3.4") <= rate_limit._MAX_FAILURES
    assert rate_limit.is_blocked("1.2.3.4") is True


def test_other_ips_unaffected():
    for _ in range(rate_limit._MAX_FAILURES):
        rate_limit.register_failure("1.2.3.4")
    assert rate_limit.is_blocked("5.6.7.8") is False


def test_success_resets_counter():
    for _ in range(rate_limit._MAX_FAILURES - 1):
        rate_limit.register_failure("9.9.9.9")
    rate_limit.reset("9.9.9.9")
    assert rate_limit.is_blocked("9.9.9.9") is False


def test_login_endpoint_returns_429_when_blocked(client, db_session, monkeypatch):
    from tests.factories import create_member

    create_member(db_session, MembershipTier.FREE)
    db_session.commit()

    monkeypatch.setattr(rate_limit, "is_blocked", lambda key: True)
    response = client.post("/api/v1/auth/login", json={"username": "nouser", "password": "wrong"})
    assert response.status_code == 429
    assert "Retry-After" in response.headers
