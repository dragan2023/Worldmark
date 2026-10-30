"""Official Meituan Travel Skill CLI adapter.

The vendor Skill specifies ``@meituan-travel/ht-ai`` and its ``ht-ai query``
contract.  This module intentionally owns no unofficial HTTP protocol and does
not persist credentials in a CLI configuration file.

版本策略：包版本**固定**（不使用 ``@latest``），避免同一份代码在不同时间跑到
不同实现；升级需人工验证后改这里的常量或部署时用 ``MEITUAN_SKILL_PACKAGE``
指定一个带明确版本号的包名。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import shutil
import subprocess
from typing import Any

logger = logging.getLogger("app.integrations.meituan")

# 经验证后手动升级；不要改成 @latest。
PINNED_PACKAGE = "@meituan-travel/ht-ai@0.0.6"


class MeituanMcpUnavailable(RuntimeError):
    """Raised when the official Skill runtime or credentials are unavailable."""


class MeituanMcpError(RuntimeError):
    """Raised when an official Skill query cannot be completed."""


def _elapsed_ms(started: datetime) -> int:
    return int((datetime.now(UTC) - started).total_seconds() * 1000)


def resolve_package() -> str:
    """返回要运行的包名；必须是带明确版本号的固定版本。"""
    candidate = (os.environ.get("MEITUAN_SKILL_PACKAGE") or PINNED_PACKAGE).strip()
    if candidate.endswith("@latest") or "@" not in candidate.split("/")[-1]:
        raise MeituanMcpUnavailable(
            "美团酒旅 Skill 必须固定版本（例如 @meituan-travel/ht-ai@0.0.6），"
            "不接受 @latest 或未指定版本。"
        )
    return candidate


@dataclass(frozen=True)
class MeituanTravelResult:
    """A raw official response plus safe metadata for downstream normalization."""

    content: str
    raw_json: dict[str, Any] | list[Any] | None
    queried_at: datetime
    source: str = "美团酒旅官方 Skill"
    provider_version: str = PINNED_PACKAGE


class MeituanTravelMcp:
    """Invoke the official ``ht-ai query`` Skill in a short-lived process."""

    channel = "meituan-developer"

    def __init__(self, token: str | None, executable: str | None = None, *, timeout_seconds: int = 120) -> None:
        self._token = token
        self._executable = executable or shutil.which("npx.cmd") or shutil.which("npx")
        self._timeout_seconds = timeout_seconds

    @property
    def package(self) -> str:
        return resolve_package()

    def is_available(self) -> bool:
        return bool(self._token and self._executable)

    def query(self, city: str, query: str, *, origin_query: str | None = None) -> MeituanTravelResult:
        if not self._token:
            raise MeituanMcpUnavailable("MEITUAN_HT_TOKEN is not configured.")
        if not self._executable:
            raise MeituanMcpUnavailable("npx is required to run the official Meituan Travel Skill.")
        city, query = city.strip(), query.strip()
        if not city:
            raise ValueError("city is required for a Meituan Travel Skill query.")
        if not query:
            raise ValueError("query is required for a Meituan Travel Skill query.")

        environment = os.environ.copy()
        environment["MEITUAN_HT_TOKEN"] = self._token
        environment["MEITUAN_RAW_JSON"] = "1"
        # The former adapter used a different vendor CLI and config-file token.
        # Do not let an inherited legacy variable affect the official runtime.
        environment.pop("MEITUAN_TRAVEL_TOKEN", None)
        command = [
            self._executable,
            "--yes",
            self.package,
            "query",
            "--query",
            query,
            "--origin-query",
            (origin_query or query).strip() or query,
            "--channel",
            self.channel,
            "--city",
            city,
            "-o",
            "json",
        ]
        started = datetime.now(UTC)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout_seconds,
                check=False,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            logger.warning("provider=meituan outcome=timeout duration_ms=%d", _elapsed_ms(started))
            raise MeituanMcpError("美团酒旅规划请求超时，请稍后重试。") from exc
        except OSError as exc:
            logger.warning("provider=meituan outcome=unavailable reason=spawn_failed")
            raise MeituanMcpUnavailable("The official Meituan Travel Skill runtime could not be started.") from exc

        if completed.returncode == 3:
            logger.warning("provider=meituan outcome=unavailable reason=token_rejected")
            raise MeituanMcpUnavailable("美团酒旅 Token 无效或未配置。")
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "官方美团酒旅 Skill 请求失败。").strip()
            logger.warning(
                "provider=meituan outcome=failed exit_code=%s duration_ms=%d",
                completed.returncode, _elapsed_ms(started),
            )
            raise MeituanMcpError(detail[:1000])

        raw_output = (completed.stdout or "").strip()
        try:
            raw_json = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            logger.warning("provider=meituan outcome=invalid_json duration_ms=%d", _elapsed_ms(started))
            raise MeituanMcpError("官方美团酒旅 Skill 未返回有效 JSON。") from exc
        if not isinstance(raw_json, (dict, list)):
            raise MeituanMcpError("官方美团酒旅 Skill 返回的 JSON 结构无效。")
        logger.info(
            "provider=meituan outcome=ok version=%s duration_ms=%d payload_chars=%d",
            self.package, _elapsed_ms(started), len(raw_output),
        )
        return MeituanTravelResult(
            content=self._display_text(raw_json),
            raw_json=raw_json,
            queried_at=datetime.now(UTC),
        )

    @staticmethod
    def _display_text(raw_json: dict[str, Any] | list[Any]) -> str:
        """Preserve an official text field when present without guessing a schema."""
        if isinstance(raw_json, dict):
            for key in ("data", "content", "answer", "message", "markdown", "text", "result"):
                value = raw_json.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return json.dumps(raw_json, ensure_ascii=False, indent=2)
