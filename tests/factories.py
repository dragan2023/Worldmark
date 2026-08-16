from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.enums import IPType, PublicationStatus, VerificationStatus
from app.models.ip_work import IPWork
from app.models.landmark import Landmark
from app.models.location import Location
from app.models.membership import Membership
from app.models.source import LandmarkSource, Source
from app.models.user import User


def create_landmark(
    db: Session,
    *,
    work_title: str = "黑神话：悟空",
    aliases: str | None = "Black Myth Wukong,悟空",
    ip_type: IPType = IPType.GAME,
    landmark_name: str = "应县木塔",
    country_code: str = "CN",
    country_name: str = "中国",
    province_name: str | None = "山西省",
    city_name: str | None = "朔州市",
    published: bool = True,
    has_coordinates: bool = True,
    ip_work: IPWork | None = None,
) -> Landmark:
    work = ip_work or IPWork(
        title=work_title,
        aliases=aliases,
        ip_type=ip_type,
        status=PublicationStatus.PUBLISHED if published else PublicationStatus.DRAFT,
    )
    location = Location(
        country_code=country_code,
        country_name=country_name,
        province_name=province_name,
        city_name=city_name,
        normalized_address=f"{province_name or country_name}{city_name or ''}{landmark_name}",
        latitude=39.57 if has_coordinates else None,
        longitude=113.17 if has_coordinates else None,
    )
    landmark = Landmark(
        ip_work=work,
        location=location,
        name=landmark_name,
        description=f"{landmark_name}的原创地标简介。",
        transit_text="从市区乘公共交通后步行可达。",
        verification_status=VerificationStatus.VERIFIED if published else VerificationStatus.CANDIDATE,
        published_at=datetime.now(UTC) if published else None,
    )
    source = Source(
        url=f"https://example.org/{work_title}/{landmark_name}",
        title="示例官方来源",
        publisher="示例机构",
        source_type="official",
        accessed_at=datetime.now(UTC),
    )
    db.add_all([work, location, landmark, source])
    db.flush()
    db.add(LandmarkSource(landmark_id=landmark.id, source_id=source.id, claim_scope="verification"))
    db.commit()
    db.refresh(landmark)
    return landmark


def create_member(db: Session, tier) -> User:
    user = User(email=f"{tier}-{db.query(User).count()}@example.org", password_hash="test-only")
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, tier=tier))
    db.commit()
    db.refresh(user)
    return user
