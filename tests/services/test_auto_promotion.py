"""M3：地标发布后贡献者自动提权（二级 → 一级）。"""

from app.models.enums import MembershipTier, VerificationStatus, UserRole
from app.models.contribution import LandmarkContribution
from app.services.review import LandmarkReviewService
from tests.factories import create_landmark, create_member


def _prepare_verified_landmark(db_session, contributor_user_id: int | None):
    landmark = create_landmark(db_session, published=False, landmark_name="提权测试地标")
    db_session.add(LandmarkContribution(
        landmark_id=landmark.id,
        contributor_name="贡献者",
        contributor_user_id=contributor_user_id,
    ))
    db_session.commit()
    landmark.verification_status = VerificationStatus.VERIFIED
    db_session.commit()
    return landmark


def test_publish_promotes_level2_contributor_to_level1(db_session):
    user = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL2.value)
    landmark = _prepare_verified_landmark(db_session, contributor_user_id=user.id)

    LandmarkReviewService(db_session).publish(landmark.id)

    db_session.refresh(user)
    assert user.role == UserRole.LEVEL1.value


def test_promotion_is_idempotent_and_never_demotes(db_session):
    user = create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)
    landmark = _prepare_verified_landmark(db_session, contributor_user_id=user.id)

    LandmarkReviewService(db_session).publish(landmark.id)

    db_session.refresh(user)
    assert user.role == UserRole.LEVEL1.value


def test_admin_contributor_stays_admin(db_session):
    user = create_member(db_session, MembershipTier.FREE, role=UserRole.ADMIN.value)
    landmark = _prepare_verified_landmark(db_session, contributor_user_id=user.id)

    LandmarkReviewService(db_session).publish(landmark.id)

    db_session.refresh(user)
    assert user.role == UserRole.ADMIN.value


def test_publish_without_contribution_is_fine(db_session):
    landmark = create_landmark(db_session, published=False, landmark_name="无贡献者地标")
    landmark.verification_status = VerificationStatus.VERIFIED
    db_session.commit()

    published = LandmarkReviewService(db_session).publish(landmark.id)
    assert published.published_at is not None
