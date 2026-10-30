"""地标文本输入的统一清洗与校验。

管理员与贡献者入口使用同一套规则：先 trim 再判空，避免「全空格名称」被保成空串。
"""

from __future__ import annotations

FIELD_LABELS = {
    "name": "地标名称",
    "description": "地标简介",
    "transit_text": "交通说明",
    "landmark_kind": "地标类型",
}

# 必填文本字段：trim 后不允许为空
REQUIRED_FIELDS = frozenset({"name", "description"})

MAX_LENGTHS = {"name": 255, "description": 20000, "transit_text": 4000, "landmark_kind": 100}


class LandmarkInputError(ValueError):
    """输入内容不合法（由 API 层映射为 422）。"""


def clean_required_text(value: str, field: str) -> str:
    text = (value or "").strip()
    if not text:
        raise LandmarkInputError(f"{FIELD_LABELS[field]}不能为空，也不能只包含空格。")
    if len(text) > MAX_LENGTHS[field]:
        raise LandmarkInputError(f"{FIELD_LABELS[field]}不能超过 {MAX_LENGTHS[field]} 个字符。")
    return text


def clean_optional_text(value: str | None) -> str | None:
    """空字符串表示「清空该字段」，返回 None；其余情况返回 trim 后的文本。"""
    text = (value or "").strip()
    return text or None


def apply_landmark_updates(landmark, payload, fields: tuple[str, ...]) -> list[str]:
    """对 payload 中显式给出的字段做清洗后写回，返回实际变更的字段名。"""
    changed: list[str] = []
    for field in fields:
        value = getattr(payload, field)
        if value is None:
            continue
        cleaned = clean_required_text(value, field) if field in REQUIRED_FIELDS else clean_optional_text(value)
        if getattr(landmark, field) == cleaned:
            continue
        setattr(landmark, field, cleaned)
        changed.append(field)
    return changed
