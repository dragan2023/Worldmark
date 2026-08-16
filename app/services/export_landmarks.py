import csv
import io
from dataclasses import dataclass
from datetime import date

from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.models.export_event import ExportEvent
from app.services.landmark_catalog import CatalogEntry, CatalogFilters, LandmarkCatalogService

EXPORT_HEADERS = ("作品名称", "地标名称", "国家/地区", "详细地址", "地标简介", "信息更新时间")
MAX_EXPORT_ROWS = 1000


class ExportValidationError(ValueError):
    """Raised when an export cannot be safely generated."""


@dataclass(frozen=True)
class ExportFile:
    content: bytes
    media_type: str
    filename: str


class LandmarkExportService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._catalog = LandmarkCatalogService(db)

    def export_csv(self, filters: CatalogFilters) -> ExportFile:
        rows = self._load_rows(filters)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(EXPORT_HEADERS)
        writer.writerows(self._row_values(row) for row in rows)
        self._record_event(filters, "csv", len(rows))
        return ExportFile(output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", self._filename(filters, "csv"))

    def export_xlsx(self, filters: CatalogFilters) -> ExportFile:
        rows = self._load_rows(filters)
        workbook = Workbook(write_only=True)
        worksheet = workbook.create_sheet("地标清单")
        worksheet.append(EXPORT_HEADERS)
        for row in rows:
            worksheet.append(self._row_values(row))
        output = io.BytesIO()
        workbook.save(output)
        self._record_event(filters, "xlsx", len(rows))
        return ExportFile(
            output.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            self._filename(filters, "xlsx"),
        )

    def _load_rows(self, filters: CatalogFilters) -> tuple[CatalogEntry, ...]:
        result = self._catalog.list(filters, page=1, page_size=MAX_EXPORT_ROWS)
        if result.total == 0:
            raise ExportValidationError("No published landmarks match the current filters.")
        if result.total > MAX_EXPORT_ROWS:
            raise ExportValidationError("Export exceeds 1,000 rows. Narrow the current filters first.")
        return result.items

    def _record_event(self, filters: CatalogFilters, file_format: str, result_count: int) -> None:
        self._db.add(
            ExportEvent(
                actor_kind="anonymous",
                file_format=file_format,
                ip_type=filters.ip_type.value if filters.ip_type else None,
                result_count=result_count,
            )
        )
        self._db.commit()

    @staticmethod
    def _row_values(row: CatalogEntry) -> tuple[str, ...]:
        return (
            row.work_title,
            row.name,
            row.country_name,
            row.normalized_address,
            row.description,
            row.updated_at.date().isoformat(),
        )

    @staticmethod
    def _filename(filters: CatalogFilters, extension: str) -> str:
        module = filters.ip_type.value if filters.ip_type else "all"
        return f"{module}-landmarks-{date.today().isoformat()}.{extension}"
