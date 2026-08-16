import sys

from app.db.session import SessionLocal
from app.services.data_quality import LandmarkDataQualityService


def main() -> int:
    with SessionLocal() as db:
        issues = LandmarkDataQualityService(db).scan_published()
    for issue in issues:
        print(f"landmark={issue.landmark_id} code={issue.code} message={issue.message}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
