"""环境代理变量的兼容处理。

httpx 0.28 解析 NO_PROXY 时会把带方括号的 IPv6 条目（[::1]）当作 host:port，
直接抛 InvalidURL: Invalid port 错误。这样所有走环境代理的客户端（高德、
DeepSeek、Nominatim、Commons 下载）在带该条目的机器上必然失败。

去掉方括号不改变语义（::1 与 [::1] 指向同一个回环地址），但能让 httpx 正常
解析。函数幂等，可重复调用。
"""

from __future__ import annotations

import os

_NO_PROXY_NAMES = ("NO_PROXY", "no_proxy")


def normalize_no_proxy() -> None:
    """把 [::1] 这类条目还原成 ::1，让 httpx 能解析代理环境变量。"""
    for name in _NO_PROXY_NAMES:
        raw = os.environ.get(name)
        if not raw:
            continue
        entries: list[str] = []
        for item in raw.split(","):
            entry = item.strip()
            if entry.startswith("[") and entry.endswith("]"):
                entry = entry[1:-1]
            if entry:
                entries.append(entry)
        normalized = ",".join(entries)
        if normalized != raw:
            os.environ[name] = normalized
