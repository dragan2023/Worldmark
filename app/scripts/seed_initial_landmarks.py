"""Import, review, and publish the project-maintained initial landmark table.

Run from the project root with:
    .\\.venv\\Scripts\\python.exe -m app.scripts.seed_initial_landmarks
"""

import csv
import io
import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.contribution import LandmarkContribution
from app.models.enums import VerificationStatus
from app.models.landmark import Landmark
from app.models.ip_work import IPWork
from app.models.source import LandmarkSource, Source
from app.services.import_landmarks import LandmarkImportService
from app.services.review import LandmarkReviewService

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed" / "landmarks_verified.csv"
CONTENT_PATH = Path(__file__).resolve().parents[2] / "data" / "seed" / "landmark_content.json"
ENTRIES_ARCHIVE_ROOT = Path(__file__).resolve().parents[2] / "data" / "contributions" / "entries" / "archive"
REVIEW_REASON = "初始表已按数据采集规范补齐详细地址、原创简介和至少一条作品关联来源。"
REVIEWER_NAME = "initial-data-review"


def main() -> None:
    db = SessionLocal()
    try:
        content = SEED_PATH.read_bytes()
        result = LandmarkImportService(db).import_csv(content)
        if result.failures:
            duplicate_only = all(failure.message == "Duplicate work, landmark name, and address." for failure in result.failures)
            if not duplicate_only:
                messages = "; ".join(f"row {item.row_number}: {item.message}" for item in result.failures)
                raise RuntimeError(f"Seed import failed: {messages}")

        reviewer = LandmarkReviewService(db)
        seed_source_urls = {
            row["source_url"]
            for row in csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
            if row.get("source_url")
        }
        pending_ids = db.scalars(
            select(Landmark.id)
            .join(LandmarkSource)
            .join(Source)
            .where(
                Source.url.in_(seed_source_urls),
                Landmark.verification_status == VerificationStatus.CANDIDATE,
                Landmark.published_at.is_(None),
            )
        ).all()
        published = 0
        for landmark_id in pending_ids:
            reviewer.review(landmark_id, VerificationStatus.VERIFIED, REVIEW_REASON, REVIEWER_NAME)
            reviewer.publish(landmark_id)
            published += 1

        synced = _sync_public_content(db)
        attributed = _write_attributions(db)
        print(f"Imported {len(result.imported_landmark_ids)} records; published {published} seed records; synchronized {synced} content records; wrote {attributed} contributor attribution(s).")
    finally:
        db.close()


def _sync_public_content(db) -> int:
    """Apply the independently editable three-part descriptions to seed records."""
    content_items = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    changed = 0
    for item in content_items:
        landmark = db.scalar(
            select(Landmark)
            .join(IPWork)
            .where(
                IPWork.ip_type == item["ip_type"],
                IPWork.title == item["work_title"],
                Landmark.name == item["landmark_name"],
            )
        )
        if landmark is None:
            raise RuntimeError(f"Missing seed landmark: {item['ip_type']} / {item['work_title']} / {item['landmark_name']}")
        if landmark.description != item["description"] or landmark.transit_text is not None:
            landmark.description = item["description"]
            landmark.transit_text = None
            changed += 1
    db.commit()
    return changed


def _load_attribution_manifests(archive_root: Path | None = None) -> list[dict[str, object]]:
    """Collect import records from every per-day manifest.json under the archive.

    Each record carries the entry file, the PR author's GitHub username and the
    imported landmark key (ip_type + work_title + landmark_name), which is what
    seed_initial_landmarks uses to write LandmarkContribution attribution rows.
    """
    archive_root = archive_root or ENTRIES_ARCHIVE_ROOT
    records: list[dict[str, object]] = []
    if not archive_root.exists():
        return records
    for manifest_path in sorted(archive_root.rglob("manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        records.extend(data.get("imports", []))
    return records


def _write_attributions(db, records: list[dict[str, object]] | None = None) -> int:
    """Create LandmarkContribution rows for manifest records with a GitHub username.

    Records whose landmark is not found or whose username is empty are skipped
    (the pre-existing behavior for rows without attribution is unchanged). The
    function is idempotent: a landmark+username pair is only written once.
    """
    if records is None:
        records = _load_attribution_manifests()
    created = 0
    for record in records:
        username = str(record.get("contributor") or "").strip()
        if not username:
            continue
        landmark = db.scalar(
            select(Landmark)
            .join(IPWork)
            .where(
                IPWork.ip_type == record.get("ip_type"),
                IPWork.title == record.get("work_title"),
                Landmark.name == record.get("landmark_name"),
            )
        )
        if landmark is None:
            continue
        exists = db.scalar(
            select(LandmarkContribution.id).where(
                LandmarkContribution.landmark_id == landmark.id,
                LandmarkContribution.contributor_name == username,
            )
        )
        if exists is not None:
            continue
        db.add(LandmarkContribution(landmark_id=landmark.id, contributor_name=username))
        created += 1
    if created:
        db.commit()
    return created


if __name__ == "__main__":
    main()
