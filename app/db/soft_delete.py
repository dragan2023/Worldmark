"""Landmark 软删除的全局查询过滤。

管理员删除地标后置 deleted_at；所有普通 SELECT 自动排除已删行，
需要看见已删行（如恢复）时在执行选项里传 include_deleted=True。
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app.models.landmark import Landmark


@event.listens_for(Session, "do_orm_execute")
def _filter_soft_deleted_landmarks(execute_state) -> None:
    if not execute_state.is_select:
        return
    if execute_state.execution_options.get("include_deleted", False):
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            Landmark,
            lambda cls: cls.deleted_at.is_(None),
            include_aliases=True,
        )
    )
