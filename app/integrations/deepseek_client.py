"""Minimal DeepSeek chat-completions client (OpenAI-compatible endpoint).

Deliberately keeps the same shape as the other integration clients in this
package: a thin ``httpx`` wrapper with an injectable transport so tests never
make a real network call.
"""

import json
from collections.abc import Mapping
from typing import Any

import httpx


class DeepSeekConfigurationError(RuntimeError):
    """Raised before a request when required local configuration is absent."""


class DeepSeekClientError(RuntimeError):
    """Raised when DeepSeek rejects, fails, or returns an unusable payload."""


def repair_truncated_json(raw: str) -> str:
    """Best-effort repair of a truncated or sloppy JSON object string.

    Handles markdown code fences, surrounding prose, trailing commas, and
    unclosed brackets/arrays so a partially-complete model response can still
    be parsed. Raises ``ValueError`` when the content is truncated inside a
    string value and cannot be salvaged (the caller should then retry).
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.lstrip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.rstrip("`").strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found")
    text = text[start:]

    cleaned: list[str] = []
    stack: list[str] = []
    in_string = False
    escaped = False
    length = len(text)
    for index, char in enumerate(text):
        if in_string:
            cleaned.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            cleaned.append(char)
        elif char == "{":
            stack.append("}")
            cleaned.append(char)
        elif char == "[":
            stack.append("]")
            cleaned.append(char)
        elif char == "}":
            if stack and stack[-1] == "}":
                stack.pop()
                cleaned.append(char)
            else:
                break
        elif char == "]":
            if stack and stack[-1] == "]":
                stack.pop()
                cleaned.append(char)
            else:
                break
        elif char == ",":
            lookahead = index + 1
            while lookahead < length and text[lookahead] in " \t\r\n":
                lookahead += 1
            if lookahead < length and text[lookahead] in "}]":
                continue
            cleaned.append(char)
        else:
            cleaned.append(char)

    if in_string:
        raise ValueError("truncated inside a string value")

    result = "".join(cleaned).rstrip()
    return result + "".join(reversed(stack))


class DeepSeekClient:
    """Client for DeepSeek's OpenAI-compatible chat completions API."""

    name = "deepseek"

    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-flash",
        thinking: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._thinking = thinking
        self._transport = transport

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> str:
        """Return the assistant text for a chat conversation."""
        payload = self._build_payload(messages, temperature=temperature)
        body = self._post(payload)
        return self._extract_content(body)

    def generate_json(
        self,
        messages: list[dict[str, str]],
        *,
        retries: int = 2,
    ) -> dict[str, Any]:
        """Request a JSON object response, parse it, and recover from bad output.

        Retries on empty content and unparseable/truncated JSON, repairing
        structural truncation locally before giving up. The request does not
        impose an output-length parameter, so the model can emit a complete document.
        """
        payload = self._build_payload(messages)
        payload["response_format"] = {"type": "json_object"}
        last_error: Exception | None = None
        for _ in range(retries + 1):
            try:
                body = self._post(payload)
            except DeepSeekConfigurationError:
                raise
            except DeepSeekClientError as exc:
                last_error = exc
                continue

            content = self._extract_content(body)
            if not content:
                last_error = DeepSeekClientError("DeepSeek returned empty content.")
                continue

            parsed = self._parse_content(content)
            if parsed is not None:
                return parsed
            last_error = DeepSeekClientError("DeepSeek returned unparseable JSON content.")
        raise last_error or DeepSeekClientError("DeepSeek failed to generate JSON.")

    @staticmethod
    def _parse_content(content: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            try:
                parsed = json.loads(repair_truncated_json(content))
            except (ValueError, json.JSONDecodeError):
                return None
        return parsed if isinstance(parsed, dict) else None

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self._model, "messages": messages, "stream": False}
        # DeepSeek V4 enables thinking mode by default; we opt out unless requested,
        # since structured generation benefits more from a deterministic, cheaper path.
        payload["thinking"] = {"type": "enabled" if self._thinking else "disabled"}
        if temperature is not None:
            payload["temperature"] = temperature
        return payload

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise DeepSeekConfigurationError("DEEPSEEK_API_KEY is not configured.")
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=60.0, transport=self._transport) as client:
                response = client.post(f"{self._base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DeepSeekClientError("DeepSeek chat completions request failed.") from exc
        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise DeepSeekClientError("DeepSeek returned a non-JSON response.") from exc
        if not isinstance(body, dict):
            raise DeepSeekClientError("DeepSeek returned an unexpected response shape.")
        return body

    @staticmethod
    def _extract_content(body: Mapping[str, Any]) -> str:
        choices = body.get("choices") or []
        if not isinstance(choices, list) or not choices:
            raise DeepSeekClientError("DeepSeek response contains no choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise DeepSeekClientError("DeepSeek response contains no message content.")
        return content.strip()
