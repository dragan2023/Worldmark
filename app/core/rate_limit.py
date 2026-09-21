"""内存级登录限速：按客户端 IP 的滑动窗口失败计数。

单进程内存实现（重启即清零），足够拦截低成本的暴力破解；
多副本部署时应替换为共享存储（Redis）实现。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_WINDOW_SECONDS = 900  # 15 分钟
_MAX_FAILURES = 8

_lock = threading.Lock()
_failures: dict[str, deque[float]] = defaultdict(deque)


def register_failure(key: str) -> int:
    """记录一次失败，返回当前窗口内的失败次数。"""
    now = time.monotonic()
    with _lock:
        bucket = _failures[key]
        bucket.append(now)
        while bucket and now - bucket[0] > _WINDOW_SECONDS:
            bucket.popleft()
        return len(bucket)


def is_blocked(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        bucket = _failures.get(key)
        if not bucket:
            return False
        while bucket and now - bucket[0] > _WINDOW_SECONDS:
            bucket.popleft()
        return len(bucket) >= _MAX_FAILURES


def reset(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


def retry_after_seconds(key: str) -> int:
    now = time.monotonic()
    with _lock:
        bucket = _failures.get(key)
        if not bucket:
            return 0
        oldest = bucket[0]
    return max(1, int(_WINDOW_SECONDS - (now - oldest)))
