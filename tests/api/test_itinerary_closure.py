"""阶段04 回归：无密钥基础规划、软删引用、编辑保留与并发、XLSX 文本、坐标边界。"""

from __future__ import annotations

import io

import httpx
import pytest
from openpyxl import load_workbook

from app.core.auth import create_access_token
from app.models.enums import MembershipTier, PublicationStatus, UserRole
from tests.factories import create_admin, create_landmark, create_member


def _headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _payload(landmark_id: int, **overrides) -> dict[str, object]:
    value: dict[str, object] = {
        "ip_type": "game",
        "work": "黑神话：悟空",
        "origin_city": "朔州",
        "start_date": "2026-09-01",
        "end_date": "2026-09-01",
        "daily_hours": 8,
        "must_visit_landmark_ids": [landmark_id],
        "lodging_mode": "none",
    }
    value.update(overrides)
    return value


@pytest.fixture()
def member(db_session):
    return create_member(db_session, MembershipTier.FREE, role=UserRole.LEVEL1.value)


# --------------------------------------------------- B07 无密钥的基础规划


def test_basic_itinerary_works_without_any_external_key(client, db_session, member):
    landmark = create_landmark(db_session, landmark_name="基础规划地标")

    created = client.post("/api/v1/itineraries", json=_payload(landmark.id), headers=_headers(member))

    assert created.status_code == 200
    body = created.json()
    assert body["generation_mode"] == "basic"
    assert body["days"][0]["stops"][0]["landmark_id"] == landmark.id
    assert body["enhancement_warnings"] == []


def test_finalize_without_supplier_reports_structured_config_error(client, db_session, member):
    landmark = create_landmark(db_session, landmark_name="增强地标")

    response = client.post("/api/v1/itineraries/finalize", json=_payload(landmark.id), headers=_headers(member))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "enhancement_unavailable"
    assert detail["reason"] == "not_configured"
    assert detail["config_url"] == "/account/api-keys"
    assert "基础规划" in detail["fallback"]


def test_form_defaults_to_basic_endpoint_and_offers_enhancement_toggle(client, db_session, member):
    anonymous = client.get("/itineraries/new", follow_redirects=False)
    assert anonymous.status_code == 303
    assert anonymous.headers["location"].startswith("/login?next=")

    page = client.get("/itineraries/new", headers=_headers(member))
    assert page.status_code == 200
    assert 'id="use-enhancement"' in page.text
    # 页面默认调用基础规划入口，外部增强是显式选项
    assert "/itineraries/finalize" in client.get("/static/js/itinerary-form.js").text


def test_request_bounds_reject_oversized_trips(client, db_session, member):
    landmark = create_landmark(db_session, landmark_name="边界地标")
    response = client.post(
        "/api/v1/itineraries",
        json=_payload(landmark.id, end_date="2026-12-31"),
        headers=_headers(member),
    )
    assert response.status_code == 422
    too_many_hours = client.post(
        "/api/v1/itineraries", json=_payload(landmark.id, daily_hours=20), headers=_headers(member)
    )
    assert too_many_hours.status_code == 422


# --------------------------------------- B05 软删/撤回后的历史行程引用


def test_soft_deleted_stop_keeps_placeholder_and_user_note(client, db_session, member):
    from datetime import UTC, datetime

    landmark = create_landmark(db_session, landmark_name="将被删除的地标")
    created = client.post(
        "/api/v1/itineraries", json=_payload(landmark.id), headers=_headers(member)
    ).json()
    itinerary_id = created["id"]

    # 用户先写下备注，再让地点被软删
    patched = client.patch(
        f"/api/v1/itineraries/{itinerary_id}",
        json={
            "expected_version": created["version"],
            "days": [{
                "day_number": 1,
                "summary": created["days"][0]["summary"],
                "stops": [{
                    "landmark_id": landmark.id,
                    "time_slot": "09:00",
                    "planned_minutes": 120,
                    "selection_reason": "用户保留",
                    "user_note": "记得带身份证",
                }],
            }],
        },
        headers=_headers(member),
    )
    assert patched.status_code == 200

    landmark.deleted_at = datetime.now(UTC)
    db_session.commit()

    detail = client.get(f"/api/v1/itineraries/{itinerary_id}", headers=_headers(member))
    assert detail.status_code == 200
    stop = detail.json()["days"][0]["stops"][0]
    assert stop["availability"] == "unavailable"
    assert stop["landmark_name"] == "地点已不可用"
    assert stop["user_note"] == "记得带身份证"
    assert stop["normalized_address"] is None

    page = client.get(f"/itineraries/{itinerary_id}", headers=_headers(member))
    assert page.status_code == 200
    assert "地点已不可用" in page.text
    assert "记得带身份证" in page.text

    for file_format in ("html", "docx", "xlsx"):
        export = client.get(f"/api/v1/itineraries/{itinerary_id}/exports/{file_format}", headers=_headers(member))
        assert export.status_code == 200, file_format
        if file_format == "html":
            assert "地点已不可用" in export.content.decode("utf-8")
        if file_format == "xlsx":
            sheet = load_workbook(io.BytesIO(export.content)).active
            values = [cell.value for row in sheet.iter_rows() for cell in row]
            assert "地点已不可用" in values


def test_retracted_landmark_stop_marks_unpublished(client, db_session, member):
    landmark = create_landmark(db_session, landmark_name="撤回测试")
    created = client.post("/api/v1/itineraries", json=_payload(landmark.id), headers=_headers(member)).json()

    landmark.published_at = None
    landmark.ip_work.status = PublicationStatus.DRAFT
    db_session.commit()

    stop = client.get(f"/api/v1/itineraries/{created['id']}", headers=_headers(member)).json()["days"][0]["stops"][0]
    assert stop["availability"] == "unavailable"
    assert stop["landmark_name"] == "撤回测试"  # 用户已看过的名称保留
    assert stop["normalized_address"] is None


def test_new_planning_cannot_select_retracted_landmark(client, db_session, member):
    landmark = create_landmark(db_session, landmark_name="已撤回不可选")
    landmark.published_at = None
    landmark.ip_work.status = PublicationStatus.DRAFT
    db_session.commit()

    response = client.post("/api/v1/itineraries", json=_payload(landmark.id), headers=_headers(member))
    assert response.status_code == 422


# --------------------------------- R03 编辑保留补充安排、预算标记与并发


def test_editing_preserves_supplemental_items_and_marks_budget_stale(client, db_session, member):
    from app.models.itinerary import ItineraryDay

    landmark = create_landmark(db_session, landmark_name="编辑保留地标")
    created = client.post("/api/v1/itineraries", json=_payload(landmark.id), headers=_headers(member)).json()

    day = db_session.query(ItineraryDay).filter_by(itinerary_id=created["id"], day_number=1).one()
    day.supplemental_items = [{"type": "行程安排", "name": "晚饭：刀削面", "time_slot": "19:00"}]
    day.travel_context = {"city": "朔州市", "lodging": {"mode": "none"}, "intercity_transport": []}
    itinerary = day.itinerary
    itinerary.budget_summary = {"budget_amount": 1000, "estimated_amount": 320, "status": "已核算", "breakdown": {}}
    db_session.commit()

    response = client.patch(
        f"/api/v1/itineraries/{created['id']}",
        json={
            "title": "改名后的行程",
            "expected_version": created["version"],
            "days": [{
                "day_number": 1,
                "summary": "编辑后的摘要",
                "stops": [{
                    "landmark_id": landmark.id,
                    "time_slot": "10:00",
                    "planned_minutes": 90,
                    "selection_reason": "用户调整",
                    "user_note": "早点到",
                }],
            }],
        },
        headers=_headers(member),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "改名后的行程"
    assert body["version"] == created["version"] + 1
    day_body = body["days"][0]
    assert day_body["supplemental_items"] == [{"type": "行程安排", "name": "晚饭：刀削面", "time_slot": "19:00"}]
    assert day_body["travel_context"]["city"] == "朔州市"
    assert day_body["stops"][0]["user_note"] == "早点到"
    assert body["budget_summary"]["needs_recalculation"] is True


def test_stale_version_update_returns_409(client, db_session, member):
    landmark = create_landmark(db_session, landmark_name="并发地标")
    created = client.post("/api/v1/itineraries", json=_payload(landmark.id), headers=_headers(member)).json()

    first = client.patch(
        f"/api/v1/itineraries/{created['id']}",
        json={"title": "第一次修改", "expected_version": created["version"]},
        headers=_headers(member),
    )
    assert first.status_code == 200

    second = client.patch(
        f"/api/v1/itineraries/{created['id']}",
        json={"title": "旧页面修改", "expected_version": created["version"]},
        headers=_headers(member),
    )
    assert second.status_code == 409


def test_overlapping_times_are_rejected(client, db_session, member):
    landmark = create_landmark(db_session, landmark_name="时间冲突地标")
    other = create_landmark(db_session, landmark_name="第二个地标", ip_work=landmark.ip_work)
    created = client.post(
        "/api/v1/itineraries",
        json=_payload(landmark.id, must_visit_landmark_ids=[landmark.id, other.id]),
        headers=_headers(member),
    ).json()

    response = client.patch(
        f"/api/v1/itineraries/{created['id']}",
        json={
            "expected_version": created["version"],
            "days": [{
                "day_number": 1,
                "stops": [
                    {"landmark_id": landmark.id, "time_slot": "10:00", "planned_minutes": 120, "selection_reason": "a"},
                    {"landmark_id": other.id, "time_slot": "11:00", "planned_minutes": 60, "selection_reason": "b"},
                ],
            }],
        },
        headers=_headers(member),
    )
    assert response.status_code == 422
    assert "重叠" in response.json()["detail"]


# ------------------------------------------- XLSX 文本与系统公式


def test_xlsx_writes_external_text_as_text_and_keeps_sum_formula(client, db_session, member):
    landmark = create_landmark(db_session, landmark_name="=1+1")
    # 把上游文本（模拟注入）写入当日安排
    created = client.post("/api/v1/itineraries", json=_payload(landmark.id), headers=_headers(member)).json()
    from app.models.itinerary import ItineraryDay

    day = db_session.query(ItineraryDay).filter_by(itinerary_id=created["id"], day_number=1).one()
    day.travel_context = {
        "city": "朔州市",
        "meituan_items": [
            {
                "type": "行程安排", "name": "=1+1", "city": "朔州市", "time_slot": "09:00",
                "planned_minutes": 60, "price": 30, "price_missing": False,
                "transport": "=HYPERLINK(\"http://evil\")", "note": "@SUM(1)",
                "category": "scenic", "source": "后台规划服务",
            }
        ],
    }
    db_session.commit()

    export = client.get(f"/api/v1/itineraries/{created['id']}/exports/xlsx", headers=_headers(member))
    workbook = load_workbook(io.BytesIO(export.content))
    sheet = workbook.active

    text_cells = [cell for row in sheet.iter_rows(min_row=3) for cell in row if cell.value == "=1+1"]
    assert text_cells, "外部文本应保留在表中"
    assert all(cell.data_type == "s" for cell in text_cells)

    formula_cells = [cell for row in sheet.iter_rows() for cell in row if isinstance(cell.value, str) and cell.value.startswith("=SUM(")]
    assert any(cell.data_type == "f" for cell in formula_cells)  # 系统汇总公式保留


# ------------------------------------------------ R04 坐标边界


def test_route_optimizer_sends_gcj02_to_amap(monkeypatch):
    from app.services.route_optimizer import RouteOptimizer

    captured: list[tuple[str, str]] = []

    class FakeAmap:
        def walking_distance(self, origin, destination):
            captured.append((origin, destination))
            return {"distance_meters": 500}

    optimizer = RouteOptimizer(FakeAmap())
    optimizer._walking_or_haversine((39.57, 113.17), (39.58, 113.18))

    assert captured, "应调用高德步行接口"
    origin_lng, origin_lat = (float(part) for part in captured[0][0].split(","))
    assert origin_lng != 113.17 and origin_lat != 39.57  # 已从 WGS-84 偏移到 GCJ-02
    assert abs(origin_lng - 113.17) < 0.01 and abs(origin_lat - 39.57) < 0.01


def test_planner_converts_amap_geocode_back_to_wgs84():
    from app.services.itinerary_planner import ItineraryPlannerService
    from app.services.geocoding import gcj02_to_wgs84

    value = "113.180000,39.580000"
    converted = ItineraryPlannerService._amap_location_to_wgs84(value)
    assert converted is not None
    latitude, longitude = converted
    expected_lng, expected_lat = gcj02_to_wgs84(113.18, 39.58)
    assert latitude == pytest.approx(expected_lat)
    assert longitude == pytest.approx(expected_lng)


# --------------------------------------------------- 导出三格式一致性


def test_three_exports_share_the_same_rows(client, db_session, member):
    landmark = create_landmark(db_session, landmark_name="导出一致性地标")
    created = client.post("/api/v1/itineraries", json=_payload(landmark.id), headers=_headers(member)).json()

    html = client.get(f"/api/v1/itineraries/{created['id']}/exports/html", headers=_headers(member)).content.decode("utf-8")
    xlsx = client.get(f"/api/v1/itineraries/{created['id']}/exports/xlsx", headers=_headers(member)).content
    docx = client.get(f"/api/v1/itineraries/{created['id']}/exports/docx", headers=_headers(member)).content

    assert "导出一致性地标" in html
    sheet = load_workbook(io.BytesIO(xlsx)).active
    assert any(cell.value == "导出一致性地标" for row in sheet.iter_rows() for cell in row)
    from docx import Document

    document = Document(io.BytesIO(docx))
    assert any("导出一致性地标" in cell.text for table in document.tables for row in table.rows for cell in row.cells)
