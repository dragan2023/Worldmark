from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.landmarks import _filters
from app.db.session import get_db
from app.models.enums import IPType
from app.services.export_landmarks import ExportValidationError, LandmarkExportService

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])


def _download(file) -> Response:
    return Response(
        content=file.content,
        media_type=file.media_type,
        headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
    )


@router.get("/landmarks.csv")
def export_landmarks_csv(
    ip_type: IPType | None = None,
    work: str | None = Query(default=None, max_length=255),
    country: str | None = Query(default=None, max_length=2),
    province: str | None = Query(default=None, max_length=100),
    city: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> Response:
    try:
        return _download(LandmarkExportService(db).export_csv(_filters(ip_type, work, country, province, city)))
    except ExportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/landmarks.xlsx")
def export_landmarks_xlsx(
    ip_type: IPType | None = None,
    work: str | None = Query(default=None, max_length=255),
    country: str | None = Query(default=None, max_length=2),
    province: str | None = Query(default=None, max_length=100),
    city: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> Response:
    try:
        return _download(LandmarkExportService(db).export_xlsx(_filters(ip_type, work, country, province, city)))
    except ExportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
