from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, require_entitlement, resolve_user_id
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.services.itinerary_planner import ItineraryNotFound, ItineraryPlannerService

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


def _user_id(db: Session, member: CurrentMember) -> int:
    """Return the member id; anonymous visitors share a persistent guest identity."""
    return resolve_user_id(db, member)


def _map_data(itinerary) -> dict:
    """Build per-day geocoded stop data for the itinerary route map."""
    days = []
    for day in sorted(itinerary.days, key=lambda value: value.day_number):
        stops = []
        for stop in sorted(day.stops, key=lambda value: value.stop_order):
            location = stop.landmark.location
            if location is None or location.latitude is None or location.longitude is None:
                continue
            stops.append(
                {
                    "order": stop.stop_order,
                    "name": stop.landmark.name,
                    "lat": location.latitude,
                    "lng": location.longitude,
                    "detail_url": f"/landmarks/{stop.landmark_id}",
                }
            )
        days.append({"day_number": day.day_number, "stops": stops})
    return {"days": days}


@router.get("/itineraries", response_class=HTMLResponse, include_in_schema=False)
def itinerary_index(
    request: Request,
    member: CurrentMember = Depends(require_entitlement("personalized_itinerary")),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    items = ItineraryPlannerService(db).list_owned(_user_id(db, member))
    return templates.TemplateResponse(request, "itineraries/index.html", {"request": request, "title": "我的个性化行程", "items": items})


@router.get("/itineraries/new", response_class=HTMLResponse, include_in_schema=False)
def itinerary_form(request: Request, _: object = Depends(require_entitlement("personalized_itinerary"))) -> HTMLResponse:
    return templates.TemplateResponse(request, "itineraries/form.html", {"request": request, "title": "生成个性化行程"})


@router.get("/itineraries/{itinerary_id}", response_class=HTMLResponse, include_in_schema=False)
def itinerary_detail(
    itinerary_id: int,
    request: Request,
    member: CurrentMember = Depends(require_entitlement("personalized_itinerary")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    try:
        itinerary = ItineraryPlannerService(db).get_owned(_user_id(db, member), itinerary_id)
    except ItineraryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    map_data = _map_data(itinerary)
    return templates.TemplateResponse(
        request,
        "itineraries/detail.html",
        {
            "request": request,
            "title": itinerary.title,
            "itinerary": itinerary,
            "map_tile_url": settings.map_tile_url,
            "map_data": map_data,
            "has_map_data": any(day["stops"] for day in map_data["days"]),
        },
    )
