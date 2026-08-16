from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, require_entitlement
from app.db.session import get_db
from app.models.itinerary import Itinerary
from app.schemas.itinerary import (
    ItineraryCreateRequest,
    ItineraryDayResponse,
    ItineraryListItem,
    ItineraryListResponse,
    ItineraryResponse,
    ItineraryStopResponse,
    ItineraryUpdateRequest,
)
from app.services.itinerary_exports import ItineraryExportService
from app.services.itinerary_planner import (
    ItineraryNotFound,
    ItineraryPlannerService,
)
from app.services.itinerary_validator import ItineraryValidationError

router = APIRouter(prefix="/api/v1/itineraries", tags=["itineraries"])


def _user_id(member: CurrentMember) -> int:
    if member.user_id is None:
        raise HTTPException(status_code=403, detail={"code": "membership_required", "upgrade_url": "/membership"})
    return member.user_id


def _response(itinerary: Itinerary) -> ItineraryResponse:
    return ItineraryResponse(
        id=itinerary.id,
        title=itinerary.title,
        status=itinerary.status,
        version=itinerary.version,
        start_date=itinerary.start_date,
        end_date=itinerary.end_date,
        daily_hours=itinerary.daily_hours,
        origin_city=itinerary.origin_city,
        return_city=itinerary.return_city,
        traveler_count=itinerary.traveler_count,
        budget_amount=itinerary.budget_amount,
        transport_preference=itinerary.transport_preference,
        auto_fill_nearby=itinerary.auto_fill_nearby,
        interests=itinerary.interests,
        lodging_mode=itinerary.lodging_mode,
        lodging_name=itinerary.lodging_name,
        lodging_address=itinerary.lodging_address,
        lodging_city=itinerary.lodging_city,
        lodging_reference=itinerary.lodging_reference,
        transport_reference=itinerary.transport_reference,
        budget_summary=itinerary.budget_summary,
        destination_country=itinerary.destination_country,
        destination_province=itinerary.destination_province,
        destination_city=itinerary.destination_city,
        generator_version=itinerary.generator_version,
        validation_error_summary=itinerary.validation_error_summary,
        created_at=itinerary.created_at,
        days=[
            ItineraryDayResponse(
                day_number=day.day_number,
                itinerary_date=day.itinerary_date,
                summary=day.summary,
                supplemental_items=day.supplemental_items,
                travel_context=day.travel_context,
                stops=[
                    ItineraryStopResponse(
                        landmark_id=stop.landmark_id,
                        stop_order=stop.stop_order,
                        time_slot=stop.time_slot,
                        planned_minutes=stop.planned_minutes,
                        selection_reason=stop.selection_reason,
                        user_note=stop.user_note,
                        landmark_name=stop.landmark.name,
                        work_title=stop.landmark.ip_work.title,
                        normalized_address=stop.landmark.location.normalized_address,
                        transit_text=stop.landmark.transit_text,
                        data_updated_at=stop.landmark.updated_at,
                    )
                    for stop in sorted(day.stops, key=lambda value: value.stop_order)
                ],
            )
            for day in sorted(itinerary.days, key=lambda value: value.day_number)
        ],
        disclaimer="计划只基于已发布 IP 地标生成；交通、票价、营业、预约、天气及安全信息请在出行前向官方确认。",
    )


@router.post("", response_model=ItineraryResponse, dependencies=[Depends(require_entitlement("personalized_itinerary"))])
def create_itinerary(
    payload: ItineraryCreateRequest,
    member: CurrentMember = Depends(require_entitlement("personalized_itinerary")),
    db: Session = Depends(get_db),
) -> ItineraryResponse:
    try:
        itinerary = ItineraryPlannerService(db).create(_user_id(member), payload)
    except ItineraryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response(itinerary)


@router.post("/finalize", response_model=ItineraryResponse, dependencies=[Depends(require_entitlement("personalized_itinerary"))])
def finalize_itinerary(
    payload: ItineraryCreateRequest,
    member: CurrentMember = Depends(require_entitlement("personalized_itinerary")),
    db: Session = Depends(get_db),
) -> ItineraryResponse:
    try:
        itinerary = ItineraryPlannerService(db).finalize(_user_id(member), payload)
    except ItineraryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response(itinerary)


@router.post("/{itinerary_id}/reprocess-meituan", response_model=ItineraryResponse, dependencies=[Depends(require_entitlement("personalized_itinerary"))])
def reprocess_meituan_itinerary(
    itinerary_id: int,
    member: CurrentMember = Depends(require_entitlement("personalized_itinerary")),
    db: Session = Depends(get_db),
) -> ItineraryResponse:
    try:
        itinerary = ItineraryPlannerService(db).reprocess_meituan_plan(_user_id(member), itinerary_id)
    except ItineraryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ItineraryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response(itinerary)


@router.post("/choice-preview", dependencies=[Depends(require_entitlement("personalized_itinerary"))])
def preview_itinerary_choices(
    payload: ItineraryCreateRequest,
    member: CurrentMember = Depends(require_entitlement("personalized_itinerary")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        _user_id(member)
        return ItineraryPlannerService(db).preview_choices(payload)
    except ItineraryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=ItineraryListResponse, dependencies=[Depends(require_entitlement("personalized_itinerary"))])
def list_itineraries(
    member: CurrentMember = Depends(require_entitlement("personalized_itinerary")), db: Session = Depends(get_db)
) -> ItineraryListResponse:
    items = ItineraryPlannerService(db).list_owned(_user_id(member))
    return ItineraryListResponse(
        items=[
            ItineraryListItem(
                id=item.id, title=item.title, status=item.status, version=item.version,
                start_date=item.start_date, end_date=item.end_date, created_at=item.created_at,
            )
            for item in items
        ]
    )


@router.get("/{itinerary_id}", response_model=ItineraryResponse, dependencies=[Depends(require_entitlement("personalized_itinerary"))])
def get_itinerary(
    itinerary_id: int, member: CurrentMember = Depends(require_entitlement("personalized_itinerary")), db: Session = Depends(get_db)
) -> ItineraryResponse:
    try:
        return _response(ItineraryPlannerService(db).get_owned(_user_id(member), itinerary_id))
    except ItineraryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{itinerary_id}", response_model=ItineraryResponse, dependencies=[Depends(require_entitlement("personalized_itinerary"))])
def update_itinerary(
    itinerary_id: int, payload: ItineraryUpdateRequest,
    member: CurrentMember = Depends(require_entitlement("personalized_itinerary")), db: Session = Depends(get_db),
) -> ItineraryResponse:
    try:
        itinerary = ItineraryPlannerService(db).update_days(_user_id(member), itinerary_id, payload.title, payload.days)
    except ItineraryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ItineraryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response(itinerary)


@router.delete("/{itinerary_id}", status_code=204, dependencies=[Depends(require_entitlement("personalized_itinerary"))])
def delete_itinerary(
    itinerary_id: int, member: CurrentMember = Depends(require_entitlement("personalized_itinerary")), db: Session = Depends(get_db)
) -> Response:
    try:
        ItineraryPlannerService(db).delete(_user_id(member), itinerary_id)
    except ItineraryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/{itinerary_id}/exports/{file_format}", dependencies=[Depends(require_entitlement("personalized_itinerary"))])
def export_itinerary(
    itinerary_id: int, file_format: str,
    member: CurrentMember = Depends(require_entitlement("personalized_itinerary")), db: Session = Depends(get_db),
) -> Response:
    try:
        itinerary = ItineraryPlannerService(db).get_owned(_user_id(member), itinerary_id)
    except ItineraryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    service = ItineraryExportService(db)
    exporters = {"html": service.export_html, "docx": service.export_docx, "xlsx": service.export_xlsx}
    if file_format not in exporters:
        raise HTTPException(status_code=404, detail="Unsupported itinerary export format.")
    file = exporters[file_format](itinerary)
    return Response(content=file.content, media_type=file.media_type, headers={"Content-Disposition": f'attachment; filename="{file.filename}"'})
