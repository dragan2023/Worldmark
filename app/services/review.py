"""地标审核与上下架状态转换的唯一实现。

所有入口（管理员条目管理、贡献者内容编辑、相册提交）都调用这里，避免各写一份
「改状态 + 动作品状态」的重复代码，也避免单条地标变更连带整个作品下架。

公开资格由 ``landmark_catalog.published_landmark_statement`` 统一定义：
未软删 AND verification_status=verified AND published_at 非空 AND 作品 published。
作品状态这里按「是否仍有公开地标」推导，不参与其他业务判断。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.contribution import LandmarkContribution
from app.models.enums import PublicationStatus, VerificationStatus, UserRole
from app.models.ip_work import IPWork
from app.models.landmark import Landmark
from app.models.review import LandmarkReview
from app.models.user import User

logger = logging.getLogger("app.review")


class ReviewValidationError(ValueError):
    """Raised when a content-review transition is invalid."""


class LandmarkReviewService:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------ 审核判定
    def review(self, landmark_id: int, decision: VerificationStatus, reason: str, reviewer_name: str) -> Landmark:
        if decision not in {VerificationStatus.VERIFIED, VerificationStatus.REJECTED}:
            raise ReviewValidationError("Review decision must be verified or rejected.")
        landmark = self._get_landmark(landmark_id)
        if not reason.strip() or not reviewer_name.strip():
            raise ReviewValidationError("A review reason and reviewer name are required.")

        landmark.verification_status = decision
        if decision == VerificationStatus.REJECTED:
            # 已发布内容被改判拒绝时必须同步撤下，否则仍会通过公开详情被读到。
            landmark.published_at = None
        self._db.add(LandmarkReview(
            landmark_id=landmark.id,
            decision=decision,
            reason=reason.strip(),
            reviewer_name=reviewer_name.strip(),
        ))
        self._sync_work_publication(landmark)
        if decision == VerificationStatus.VERIFIED:
            self._promote_contributor(landmark)
        self._db.commit()
        self._db.refresh(landmark)
        return landmark

    def publish(self, landmark_id: int) -> Landmark:
        landmark = self._get_landmark(landmark_id)
        if landmark.verification_status != VerificationStatus.VERIFIED:
            raise ReviewValidationError("Only verified landmarks can be published.")
        if not landmark.sources:
            raise ReviewValidationError("A landmark needs at least one source before publication.")
        landmark.published_at = datetime.now(UTC)
        self._promote_contributor(landmark)
        self._sync_work_publication(landmark)
        self._db.commit()
        self._db.refresh(landmark)
        return landmark

    # ------------------------------------------------------ 上下架与软删
    def unpublish(self, landmark_id: int, actor: str = "") -> Landmark:
        """只撤下这一条，同作品其他已发布地标不受影响。"""
        landmark = self._get_landmark(landmark_id)
        landmark.published_at = None
        logger.info("landmark unpublish id=%s actor=%s", landmark.id, actor or "-")
        self._sync_work_publication(landmark)
        self._db.commit()
        self._db.refresh(landmark)
        return landmark

    def request_rereview(self, landmark_id: int, actor: str = "", reason: str = "") -> Landmark:
        """贡献者修改内容或相册：回到待审核并暂时下架，等待重新核验。"""
        landmark = self._get_landmark(landmark_id)
        landmark.verification_status = VerificationStatus.CANDIDATE
        landmark.published_at = None
        self._db.add(LandmarkReview(
            landmark_id=landmark.id,
            decision=VerificationStatus.CANDIDATE,
            reason=(reason.strip() or "贡献者修改内容或相册，进入重新审核。"),
            reviewer_name=(actor.strip() or "system")[:255],
        ))
        self._sync_work_publication(landmark)
        self._db.commit()
        self._db.refresh(landmark)
        return landmark

    def soft_delete(self, landmark_id: int, actor: str = "") -> Landmark:
        landmark = self._get_landmark(landmark_id)
        landmark.deleted_at = datetime.now(UTC)
        logger.info("landmark soft delete id=%s actor=%s", landmark.id, actor or "-")
        self._sync_work_publication(landmark)
        self._db.commit()
        self._db.refresh(landmark)
        return landmark

    def restore(self, landmark_id: int, actor: str = "") -> Landmark:
        """撤销软删。不越过审核要求：未核验/未发布的地标恢复后依旧不公开。"""
        landmark = self._db.scalar(
            select(Landmark)
            .options(selectinload(Landmark.sources), selectinload(Landmark.ip_work))
            .where(Landmark.id == landmark_id)
            .execution_options(include_deleted=True)
        )
        if landmark is None:
            raise ReviewValidationError("Landmark not found.")
        if landmark.deleted_at is not None:
            landmark.deleted_at = None
        logger.info("landmark restore id=%s actor=%s", landmark.id, actor or "-")
        self._sync_work_publication(landmark)
        self._db.commit()
        self._db.refresh(landmark)
        return landmark

    # ------------------------------------------------------------ 内部工具
    def _sync_work_publication(self, landmark: Landmark) -> None:
        """作品状态按「是否仍有公开地标」推导，绝不因单条变更牵连其他条目。"""
        # 会话关闭了 autoflush，统计前必须显式 flush，否则读到的是旧 published_at。
        self._db.flush()
        work = landmark.ip_work or self._db.get(IPWork, landmark.ip_work_id)
        if work is None or work.status == PublicationStatus.ARCHIVED:
            return
        public_count = self._db.scalar(
            select(func.count())
            .select_from(Landmark)
            .where(
                Landmark.ip_work_id == work.id,
                Landmark.deleted_at.is_(None),
                Landmark.published_at.is_not(None),
                Landmark.verification_status == VerificationStatus.VERIFIED,
            )
            .execution_options(include_deleted=True)
        )
        work.status = PublicationStatus.PUBLISHED if public_count else PublicationStatus.DRAFT

    def _promote_contributor(self, landmark: Landmark) -> None:
        """发布即「通过上架」：贡献者从二级自动升为一级（幂等，只升不降）。"""
        contribution = self._db.scalar(
            select(LandmarkContribution)
            .where(LandmarkContribution.landmark_id == landmark.id)
            .order_by(LandmarkContribution.id.asc())
            .limit(1)
        )
        if contribution is None or contribution.contributor_user_id is None:
            return
        user = self._db.get(User, contribution.contributor_user_id)
        if user is not None and user.role == UserRole.LEVEL2.value:
            user.role = UserRole.LEVEL1.value

    def _get_landmark(self, landmark_id: int) -> Landmark:
        landmark = self._db.scalar(
            select(Landmark)
            .options(selectinload(Landmark.sources), selectinload(Landmark.ip_work))
            .where(Landmark.id == landmark_id)
        )
        if landmark is None:
            raise ReviewValidationError("Landmark not found.")
        return landmark
