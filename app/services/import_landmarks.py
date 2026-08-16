import csv
import io
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import IPType, PublicationStatus, VerificationStatus
from app.models.ip_work import IPWork
from app.models.landmark import Landmark
from app.models.location import Location
from app.models.source import LandmarkSource, Source

REQUIRED_COLUMNS = {
    "ip_type", "work_title", "landmark_name", "country_code", "country_name", "normalized_address",
    "description", "source_url", "source_type", "accessed_at",
}


class CandidateRow(BaseModel):
    ip_type: IPType
    work_title: str = Field(min_length=1, max_length=255)
    aliases: str | None = None
    landmark_name: str = Field(min_length=1, max_length=255)
    country_code: str = Field(min_length=2, max_length=2)
    country_name: str = Field(min_length=1, max_length=100)
    province_name: str | None = None
    city_name: str | None = None
    district_name: str | None = None
    normalized_address: str = Field(min_length=1, max_length=500)
    latitude: float | None = None
    longitude: float | None = None
    description: str = Field(min_length=1)
    transit_text: str | None = None
    landmark_kind: str | None = None
    source_url: str
    source_publisher: str | None = None
    source_title: str | None = None
    source_type: str = Field(min_length=1, max_length=100)
    accessed_at: datetime
    license_note: str | None = None
    claim_scope: str = "candidate_discovery"

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def blank_coordinates_are_missing(cls, value: object) -> object:
        """Allow the documented CSV template to leave optional coordinates empty."""
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("source_url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an http or https URL")
        return value


@dataclass(frozen=True)
class ImportFailure:
    row_number: int
    message: str


@dataclass(frozen=True)
class ImportResult:
    imported_landmark_ids: tuple[int, ...]
    failures: tuple[ImportFailure, ...]


class LandmarkImportService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def import_csv(self, content: bytes) -> ImportResult:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            return ImportResult((), (ImportFailure(1, f"Missing required columns: {', '.join(sorted(missing))}"),))

        parsed_rows: list[tuple[int, CandidateRow]] = []
        failures: list[ImportFailure] = []
        for row_number, raw_row in enumerate(reader, start=2):
            try:
                parsed_rows.append((row_number, CandidateRow.model_validate(raw_row)))
            except ValidationError as exc:
                failures.append(ImportFailure(row_number, exc.errors(include_url=False)[0]["msg"]))
        if failures:
            return ImportResult((), tuple(failures))

        imported_ids: list[int] = []
        for row_number, row in parsed_rows:
            landmark = self._create_candidate(row_number, row, failures)
            if landmark is not None:
                imported_ids.append(landmark.id)
        if failures:
            self._db.rollback()
            return ImportResult((), tuple(failures))
        self._db.commit()
        return ImportResult(tuple(imported_ids), ())

    def create_candidate(self, row: CandidateRow) -> Landmark:
        """Create one validated candidate inside the caller's transaction."""
        failures: list[ImportFailure] = []
        landmark = self._create_candidate(1, row, failures)
        if landmark is None or failures:
            message = failures[0].message if failures else "Unable to create candidate."
            raise ValueError(message)
        return landmark

    def _create_candidate(self, row_number: int, row: CandidateRow, failures: list[ImportFailure]) -> Landmark | None:
        work = self._db.scalar(select(IPWork).where(IPWork.title == row.work_title, IPWork.ip_type == row.ip_type))
        if work is None:
            work = IPWork(title=row.work_title, aliases=row.aliases, ip_type=row.ip_type, status=PublicationStatus.DRAFT)
            self._db.add(work)
            self._db.flush()

        location = self._db.scalar(
            select(Location).where(
                Location.country_code == row.country_code,
                Location.normalized_address == row.normalized_address,
            )
        )
        if location is None:
            location = Location(
                country_code=row.country_code, country_name=row.country_name, province_name=row.province_name,
                city_name=row.city_name, district_name=row.district_name, normalized_address=row.normalized_address,
                latitude=row.latitude, longitude=row.longitude,
            )
            self._db.add(location)
            self._db.flush()

        duplicate = self._db.scalar(
            select(Landmark.id).where(
                Landmark.ip_work_id == work.id, Landmark.location_id == location.id, Landmark.name == row.landmark_name
            )
        )
        if duplicate is not None:
            failures.append(ImportFailure(row_number, "Duplicate work, landmark name, and address."))
            return None

        source = self._db.scalar(select(Source).where(Source.url == row.source_url))
        if source is None:
            source = Source(
                url=row.source_url, publisher=row.source_publisher, title=row.source_title, accessed_at=row.accessed_at,
                license_note=row.license_note, source_type=row.source_type,
            )
            self._db.add(source)
            self._db.flush()

        landmark = Landmark(
            ip_work_id=work.id, location_id=location.id, name=row.landmark_name, description=row.description,
            transit_text=row.transit_text, landmark_kind=row.landmark_kind,
            verification_status=VerificationStatus.CANDIDATE,
        )
        self._db.add(landmark)
        self._db.flush()
        self._db.add(LandmarkSource(landmark_id=landmark.id, source_id=source.id, claim_scope=row.claim_scope))
        return landmark
