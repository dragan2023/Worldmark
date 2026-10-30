from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, require_page_role
from app.models.enums import UserRole
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.services.itinerary_planner import ItineraryNotFound, ItineraryPlannerService
from app.services.landmark_catalog import CatalogNotFound, LandmarkCatalogService

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


def _user_id(member: CurrentMember) -> int:
    """已认证会员 id；页面守卫已保证登录且角色不低于 level1。"""
    assert member.user_id is not None  # 由 require_page_role 保证
    return member.user_id


def _attach_display_fields(itinerary) -> None:
    """给行程站点挂上展示字段：地点不可用时给占位，模板不直接依赖 ORM 关系。"""
    for day in itinerary.days:
        for stop in day.stops:
            landmark = stop.landmark
            if landmark is None:
                stop.display_name = "地点已不可用"
                stop.display_address = ""
                stop.display_transit = "该地点已下架或删除，保留你的安排与备注。"
                stop.is_available = False
                continue
            is_public = (
                landmark.published_at is not None
                and landmark.ip_work is not None
                and getattr(landmark.ip_work.status, "value", landmark.ip_work.status) == "published"
            )
            stop.display_name = landmark.name
            stop.display_address = landmark.location.normalized_address if landmark.location else ""
            stop.display_transit = landmark.transit_text or "暂无交通文字说明。"
            stop.is_available = is_public
            if not is_public:
                stop.display_transit = "该地点当前未公开，内容可能仍在重新审核；出发前请以官方信息确认。"


def _edit_payload(itinerary) -> dict:
    return {
        "id": itinerary.id,
        "version": itinerary.version,
        "title": itinerary.title,
        "days": [
            {
                "day_number": day.day_number,
                "summary": day.summary,
                "stops": [
                    {
                        "landmark_id": stop.landmark_id,
                        "time_slot": stop.time_slot,
                        "planned_minutes": stop.planned_minutes,
                        "selection_reason": stop.selection_reason,
                        "user_note": stop.user_note,
                        "name": getattr(stop, "display_name", None) or f"地标 {stop.landmark_id}",
                    }
                    for stop in sorted(day.stops, key=lambda value: value.stop_order)
                ],
            }
            for day in sorted(itinerary.days, key=lambda value: value.day_number)
        ],
    }


def _map_data(itinerary) -> dict:
    """Build per-day geocoded stop data for the itinerary route map."""
    days = []
    for day in sorted(itinerary.days, key=lambda value: value.day_number):
        stops = []
        for stop in sorted(day.stops, key=lambda value: value.stop_order):
            landmark = stop.landmark
            # 地点被软删时 relation 为空：跳过坐标，但保留该站在页面上的占位
            if landmark is None or landmark.location is None:
                continue
            location = landmark.location
            if location.latitude is None or location.longitude is None:
                continue
            stops.append(
                {
                    "order": stop.stop_order,
                    "name": landmark.name,
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
    member: CurrentMember = Depends(require_page_role(UserRole.LEVEL1)),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    items = ItineraryPlannerService(db).list_owned(_user_id(member))
    return templates.TemplateResponse(request, "itineraries/index.html", {"request": request, "title": "我的个性化行程", "items": items})


@router.get("/itineraries/new", response_class=HTMLResponse, include_in_schema=False)
def itinerary_form(
    request: Request,
    landmark_id: int | None = None,
    _: CurrentMember = Depends(require_page_role(UserRole.LEVEL1)),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """新建行程页；`landmark_id` 只用于预选公开地标，展示文案仍以服务端数据为准。"""
    preselect = None
    if landmark_id is not None:
        try:
            entry = LandmarkCatalogService(db).get_detail(landmark_id)
        except CatalogNotFound:
            entry = None
        if entry is not None:
            preselect = {
                "id": entry.id,
                "name": entry.name,
                "city": entry.city_name or entry.province_name or "国内",
            }
    return templates.TemplateResponse(
        request,
        "itineraries/form.html",
        {"request": request, "title": "生成行程", "preselect": preselect},
    )


@router.get("/itineraries/{itinerary_id}", response_class=HTMLResponse, include_in_schema=False)
def itinerary_detail(
    itinerary_id: int,
    request: Request,
    member: CurrentMember = Depends(require_page_role(UserRole.LEVEL1)),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    try:
        itinerary = ItineraryPlannerService(db).get_owned(_user_id(member), itinerary_id)
    except ItineraryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _attach_display_fields(itinerary)
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
            "edit_data": _edit_payload(itinerary),
        },
    )
