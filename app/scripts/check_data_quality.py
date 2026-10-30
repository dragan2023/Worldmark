"""已发布地标的数据质量检查。

用法：
    .venv\\Scripts\\python.exe -m app.scripts.check_data_quality            # 扫描当前库
    .venv\\Scripts\\python.exe -m app.scripts.check_data_quality --self-test # 用合成样本自检

`--self-test` 会构造「一条合格 + 一条缺来源/缺地理信息」的合成数据，确认检查器能真的
发现问题；否则在空库上跑出「0 问题」并不能说明内容可靠。
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.services.data_quality import LandmarkDataQualityService


def _scan_current_database() -> int:
    with SessionLocal() as db:
        issues = LandmarkDataQualityService(db).scan_published()
    for issue in issues:
        print(f"landmark={issue.landmark_id} code={issue.code} message={issue.message}")
    print(f"issues={len(issues)}")
    return 1 if issues else 0


def _self_test() -> int:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models import Base
    from app.models.enums import IPType, PublicationStatus, VerificationStatus
    from app.models.ip_work import IPWork
    from app.models.landmark import Landmark
    from app.models.location import Location
    from app.models.source import LandmarkSource, Source

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        work = IPWork(title="自检作品", ip_type=IPType.GAME, status=PublicationStatus.PUBLISHED)
        session.add(work)
        session.flush()
        good = Landmark(
            ip_work=work,
            location=Location(country_code="CN", country_name="中国", normalized_address="山西省朔州市应县木塔"),
            name="自检合格地标",
            description="合格的合成简介。",
            verification_status=VerificationStatus.VERIFIED,
            published_at=now,
        )
        bad = Landmark(
            ip_work=work,
            location=Location(country_code="", country_name="", normalized_address=""),
            name="自检问题地标",
            description="   ",
            verification_status=VerificationStatus.CANDIDATE,
            published_at=now,
        )
        session.add_all([good, bad])
        session.flush()
        source = Source(url="https://example.org/selftest", title="自检来源", source_type="official", accessed_at=now)
        session.add(source)
        session.flush()
        session.add(LandmarkSource(landmark_id=good.id, source_id=source.id, claim_scope="verification"))
        session.commit()

        issues = LandmarkDataQualityService(session).scan_published()
        by_landmark: dict[int, set[str]] = {}
        for issue in issues:
            by_landmark.setdefault(issue.landmark_id, set()).add(issue.code)

        problems: list[str] = []
        if good.id in by_landmark:
            problems.append(f"合格样本被误报：{sorted(by_landmark[good.id])}")
        expected = {"missing_geography", "missing_description", "missing_source", "published_unverified"}
        if by_landmark.get(bad.id, set()) != expected:
            problems.append(f"问题样本应命中 {sorted(expected)}，实际 {sorted(by_landmark.get(bad.id, set()))}")

    engine.dispose()
    if problems:
        for problem in problems:
            print(problem)
        return 1
    print("self-test ok: 合格样本 0 问题，问题样本命中全部 4 类缺陷")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return _self_test()
    return _scan_current_database()


if __name__ == "__main__":
    sys.exit(main())
