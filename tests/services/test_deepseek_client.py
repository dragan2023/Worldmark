import json

import httpx
import pytest

from app.integrations.deepseek_client import (
    DeepSeekClient,
    DeepSeekClientError,
    DeepSeekConfigurationError,
    repair_truncated_json,
)


def _client(handler) -> DeepSeekClient:
    return DeepSeekClient("test-key", transport=httpx.MockTransport(handler))


def test_chat_returns_message_content():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "deepseek-v4-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["messages"][0]["role"] == "user"
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "你好"}}]})

    assert _client(handler).chat([{"role": "user", "content": "hi"}]) == "你好"


def test_generate_json_forces_json_object_and_parses_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer": 42}'}}]})

    result = _client(handler).generate_json([{"role": "user", "content": "给我 json"}])
    assert result == {"answer": 42}


def test_missing_key_raises_configuration_error():
    with pytest.raises(DeepSeekConfigurationError):
        DeepSeekClient(None).chat([{"role": "user", "content": "hi"}])


def test_non_json_content_raises_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "不是 json"}}]})

    with pytest.raises(DeepSeekClientError):
        _client(handler).generate_json([{"role": "user", "content": "给我 json"}])


def test_empty_choices_raise_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(DeepSeekClientError):
        _client(handler).chat([{"role": "user", "content": "hi"}])


def test_thinking_mode_can_be_enabled():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "enabled"}
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = DeepSeekClient("test-key", thinking=True, transport=httpx.MockTransport(handler))
    assert client.chat([{"role": "user", "content": "hi"}]) == "ok"


def test_repair_closes_unclosed_brackets():
    truncated = '{"days": [{"day_number": 1, "stops": [{"landmark_id": 1, "planned_minutes": 90}'
    repaired = repair_truncated_json(truncated)
    assert json.loads(repaired) == {"days": [{"day_number": 1, "stops": [{"landmark_id": 1, "planned_minutes": 90}]}]}


def test_repair_strips_trailing_comma():
    assert json.loads(repair_truncated_json('{"a": 1,}')) == {"a": 1}
    assert json.loads(repair_truncated_json('{"stops": [1, 2,],}')) == {"stops": [1, 2]}


def test_repair_strips_markdown_fence():
    fenced = '```json\n{"a": 1}\n```'
    assert json.loads(repair_truncated_json(fenced)) == {"a": 1}


def test_repair_rejects_truncated_string():
    with pytest.raises(ValueError, match="string"):
        repair_truncated_json('{"name": "未闭合')


def test_generate_json_retries_after_empty_content():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer": 42}'}}]})

    result = _client(handler).generate_json([{"role": "user", "content": "给我 json"}])
    assert result == {"answer": 42}
    assert calls["count"] == 2


def test_generate_json_recovers_truncated_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"days": [{"day_number": 1, "stops": [{"landmark_id": 1}'}}]})

    result = _client(handler).generate_json([{"role": "user", "content": "给我 json"}])
    assert result == {"days": [{"day_number": 1, "stops": [{"landmark_id": 1}]}]}


def test_generate_json_uses_the_complete_structured_generation_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert set(body) == {"model", "messages", "stream", "thinking", "response_format"}
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})

    _client(handler).generate_json([{"role": "user", "content": "给我 json"}])
