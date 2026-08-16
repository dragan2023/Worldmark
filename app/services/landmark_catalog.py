from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import IPType, PublicationStatus
from app.models.contribution import LandmarkContribution
from app.models.ip_work import IPWork
from app.models.landmark import Landmark
from app.models.location import Location
from app.models.source import LandmarkSource


class CatalogNotFound(ValueError):
    """Raised when a public landmark detail is absent or not published."""


@dataclass(frozen=True)
class CatalogFilters:
    ip_type: IPType | None = None
    work: str | None = None
    country: str | None = None
    province: str | None = None
    city: str | None = None
    landmark: str | None = None
    query: str | None = None

    @classmethod
    def from_values(
        cls,
        ip_type: IPType | None = None,
        work: str | None = None,
        country: str | None = None,
        province: str | None = None,
        city: str | None = None,
        landmark: str | None = None,
        query: str | None = None,
    ) -> "CatalogFilters":
        return cls(
            ip_type=ip_type,
            work=work.strip() or None if work else None,
            country=country.strip().upper() or None if country else None,
            province=province.strip() or None if province else None,
            city=city.strip() or None if city else None,
            landmark=landmark.strip() or None if landmark else None,
            query=query.strip() or None if query else None,
        )


@dataclass(frozen=True)
class CatalogEntry:
    id: int
    ip_type: IPType
    work_id: int
    work_title: str
    name: str
    country_code: str
    country_name: str
    province_name: str | None
    city_name: str | None
    normalized_address: str
    district_name: str | None
    description: str
    transit_text: str | None
    updated_at: object
    sources: tuple[dict[str, object], ...] = ()
    contributors: tuple[str, ...] = ()
    thumbnail_url: str | None = None

    @property
    def description_summary(self) -> str:
        return self.description if len(self.description) <= 120 else f"{self.description[:117].rstrip()}..."


@dataclass(frozen=True)
class CatalogPage:
    items: tuple[CatalogEntry, ...]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size) if self.total else 1


@dataclass(frozen=True)
class FilterOption:
    value: str
    label: str


@dataclass(frozen=True)
class RegionOption:
    name: str
    country_code: str
    province_name: str | None = None


@dataclass(frozen=True)
class FilterOptions:
    countries: tuple[FilterOption, ...]
    provinces: tuple[RegionOption, ...]
    cities: tuple[RegionOption, ...]


@dataclass(frozen=True)
class WorkCatalog:
    work_id: int
    title: str
    ip_type: IPType
    creator: str | None
    release_year: int | None
    synopsis: str | None
    aliases: str | None
    landmarks: tuple[CatalogEntry, ...]
    total: int


class LandmarkCatalogService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list(self, filters: CatalogFilters, page: int = 1, page_size: int = 20) -> CatalogPage:
        return self._paginate(published_landmark_statement(filters), page, page_size)

    def search(self, query: str, page: int = 1, page_size: int = 20) -> CatalogPage:
        pattern = f"%{query.strip()}%"
        statement = (
            select(Landmark)
            .join(Landmark.ip_work)
            .join(Landmark.location)
            .where(Landmark.published_at.is_not(None), IPWork.status == PublicationStatus.PUBLISHED)
            .where(or_(IPWork.title.ilike(pattern), IPWork.aliases.ilike(pattern), Landmark.name.ilike(pattern)))
        )
        return self._paginate(statement, page, page_size)

    def _paginate(self, statement, page: int, page_size: int) -> CatalogPage:
        if page < 1:
            raise ValueError("page must be at least 1")
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")

        total = int(self._db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        landmarks = self._db.scalars(
            statement
            .options(
                selectinload(Landmark.ip_work),
                selectinload(Landmark.location),
                selectinload(Landmark.sources).selectinload(LandmarkSource.source),
                selectinload(Landmark.contributions),
            )
            .order_by(Landmark.published_at.desc(), Landmark.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return CatalogPage(tuple(self._to_entry(landmark) for landmark in landmarks), total, page, page_size)

    def filter_options(self, ip_type: IPType | None = None) -> FilterOptions:
        statement = (
            select(Location.country_code, Location.country_name, Location.province_name, Location.city_name)
            .join(Landmark, Landmark.location_id == Location.id)
            .join(IPWork, Landmark.ip_work_id == IPWork.id)
            .where(Landmark.published_at.is_not(None), IPWork.status == PublicationStatus.PUBLISHED)
        )
        if ip_type is not None:
            statement = statement.where(IPWork.ip_type == ip_type)

        countries: dict[str, str] = {}
        provinces: dict[str, RegionOption] = {}
        cities: dict[str, RegionOption] = {}
        for country_code, country_name, province_name, city_name in self._db.execute(statement).all():
            if country_code:
                countries.setdefault(country_code, country_name or country_code)
            if province_name:
                provinces.setdefault(province_name, RegionOption(province_name, country_code))
            if city_name:
                cities.setdefault(city_name, RegionOption(city_name, country_code, province_name))

        return FilterOptions(
            countries=tuple(FilterOption(code, label) for code, label in sorted(countries.items())),
            provinces=tuple(sorted(provinces.values(), key=lambda option: option.name)),
            cities=tuple(sorted(cities.values(), key=lambda option: option.name)),
        )

    def get_work(self, work_id: int) -> WorkCatalog:
        work = self._db.scalar(select(IPWork).where(IPWork.id == work_id, IPWork.status == PublicationStatus.PUBLISHED))
        if work is None:
            raise CatalogNotFound("Published work not found.")
        landmarks = self._db.scalars(
            published_landmark_statement(CatalogFilters())
            .where(Landmark.ip_work_id == work_id)
            .options(
                selectinload(Landmark.ip_work),
                selectinload(Landmark.location),
                selectinload(Landmark.sources).selectinload(LandmarkSource.source),
                selectinload(Landmark.contributions),
            )
            .order_by(Landmark.published_at.desc(), Landmark.id.desc())
        ).all()
        entries = tuple(self._to_entry(landmark) for landmark in landmarks)
        return WorkCatalog(
            work_id=work.id,
            title=work.title,
            ip_type=work.ip_type,
            creator=work.creator,
            release_year=work.release_year,
            synopsis=work.synopsis,
            aliases=work.aliases,
            landmarks=entries,
            total=len(entries),
        )

    def get_detail(self, landmark_id: int) -> CatalogEntry:
        landmark = self._db.scalar(
            published_landmark_statement(CatalogFilters())
            .where(Landmark.id == landmark_id)
            .options(
                selectinload(Landmark.ip_work),
                selectinload(Landmark.location),
                selectinload(Landmark.sources).selectinload(LandmarkSource.source),
                selectinload(Landmark.contributions),
            )
        )
        if landmark is None:
            raise CatalogNotFound("Published landmark not found.")
        return self._to_entry(landmark)

    @staticmethod
    def _to_entry(landmark: Landmark) -> CatalogEntry:
        return CatalogEntry(
            id=landmark.id,
            ip_type=landmark.ip_work.ip_type,
            work_id=landmark.ip_work_id,
            work_title=landmark.ip_work.title,
            name=landmark.name,
            country_code=landmark.location.country_code,
            country_name=landmark.location.country_name,
            province_name=landmark.location.province_name,
            city_name=landmark.location.city_name,
            normalized_address=landmark.location.normalized_address,
            district_name=landmark.location.district_name,
            description=landmark.description,
            transit_text=landmark.transit_text,
            updated_at=landmark.updated_at,
            sources=tuple(
                {
                    "title": item.source.title,
                    "publisher": item.source.publisher,
                    "url": item.source.url,
                    "accessed_at": item.source.accessed_at,
                }
                for item in landmark.sources
                if item.source is not None
            ),
            contributors=tuple(
                contribution.contributor_name
                for contribution in sorted(landmark.contributions, key=lambda item: item.created_at)
            ),
        )



def published_landmark_statement(filters: CatalogFilters):
    """Return the shared public-catalog SQL statement without loading private coordinates."""
    statement = (
        select(Landmark)
        .join(Landmark.ip_work)
        .join(Landmark.location)
        .where(Landmark.published_at.is_not(None), IPWork.status == PublicationStatus.PUBLISHED)
    )
    if filters.ip_type is not None:
        statement = statement.where(IPWork.ip_type == filters.ip_type)
    if filters.query:
        pattern = f"%{filters.query}%"
        statement = statement.where(or_(Landmark.name.ilike(pattern), IPWork.title.ilike(pattern), IPWork.aliases.ilike(pattern)))
    if filters.work:
        pattern = f"%{filters.work}%"
        statement = statement.where(or_(IPWork.title.ilike(pattern), IPWork.aliases.ilike(pattern)))
    if filters.landmark:
        statement = statement.where(Landmark.name.ilike(f"%{filters.landmark}%"))
    if filters.country:
        statement = statement.where(Location.country_code == filters.country)
    if filters.province:
        statement = statement.where(Location.province_name == filters.province)
    if filters.city:
        statement = statement.where(Location.city_name == filters.city)
    return statement
