"""NO_PROXY 归一化：保证 httpx 能解析带方括号的 IPv6 回环条目。"""

import os

from app.core.http_env import normalize_no_proxy


def test_bracketed_ipv6_entry_is_unwrapped(monkeypatch) -> None:
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,::1,[::1]")

    normalize_no_proxy()

    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1,::1,::1"


def test_normalized_value_is_stable(monkeypatch) -> None:
    monkeypatch.setenv("no_proxy", "api.example.com,::1")

    normalize_no_proxy()
    normalize_no_proxy()

    assert os.environ["no_proxy"] == "api.example.com,::1"


def test_absent_value_is_left_alone(monkeypatch) -> None:
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

    normalize_no_proxy()

    assert "NO_PROXY" not in os.environ
    assert "no_proxy" not in os.environ
