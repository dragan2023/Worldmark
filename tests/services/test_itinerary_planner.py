from datetime import date

import pytest

from app.core.config import Settings
from app.models.enums import IPType, MembershipTier
from app.schemas.itinerary import ItineraryCreateRequest, ItineraryDayEdit, ItineraryStopEdit
from app.services.itinerary_planner import ItineraryPlannerService
from app.services.itinerary_validator import ItineraryValidationError, ItineraryValidator
from tests.factories import create_landmark, create_member


def _request(**overrides) -> ItineraryCreateRequest:
    values = {
        "title": "悟空山西两日游",
            "ip_type": IPType.GAME,
            "work": "黑神话：悟空",
        "origin_city": "朔州",
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 9, 2),
        "daily_hours": 8,
    }
    values.update(overrides)
    return ItineraryCreateRequest(**values)


def test_planner_uses_only_published_candidates_and_honors_required_stop(db_session):
    required = create_landmark(db_session, landmark_name="必去地标")
    create_landmark(db_session, landmark_name="普通地标")
    create_landmark(db_session, landmark_name="候选地标", published=False)
    member = create_member(db_session, MembershipTier.PREMIUM)

    itinerary = ItineraryPlannerService(db_session).create(member.id, _request(must_visit_landmark_ids=[required.id]))

    stop_ids = [stop.landmark_id for day in itinerary.days for stop in day.stops]
    assert itinerary.status.value == "succeeded"
    assert stop_ids[0] == required.id
    assert itinerary.generator_version == "deterministic-v2"
    assert len(itinerary.days) == 2
    assert itinerary.days[0].travel_context["lodging"]["note"]


def test_planner_allows_repeated_generation_and_edit_validator(db_session):
    landmark = create_landmark(db_session)
    member = create_member(db_session, MembershipTier.PREMIUM)
    service = ItineraryPlannerService(db_session, Settings())
    itinerary = service.create(member.id, _request(end_date=date(2026, 9, 1)))

    second = service.create(member.id, _request(title="第二份", end_date=date(2026, 9, 1)))
    with pytest.raises(ItineraryValidationError, match="outside the published candidate set"):
        service.update_days(
            member.id,
            itinerary.id,
            None,
            [ItineraryDayEdit(day_number=1, stops=[ItineraryStopEdit(landmark_id=99999, time_slot="09:00", planned_minutes=60, selection_reason="测试")])],
        )
    assert landmark.id in itinerary.candidate_landmark_ids
    assert second.id != itinerary.id


def test_validator_allows_any_positive_number_of_daily_stops():
    class Stop:
        landmark_id = 1
        planned_minutes = 60

    class Day:
        day_number = 1
        stops = [Stop()] * 7

    ItineraryValidator().validate_days([Day()], {1}, 1)


def test_planner_allows_an_eight_day_itinerary(db_session):
    landmark = create_landmark(db_session)
    member = create_member(db_session, MembershipTier.PREMIUM)

    itinerary = ItineraryPlannerService(db_session).create(
        member.id,
        _request(start_date=date(2026, 9, 1), end_date=date(2026, 9, 8), must_visit_landmark_ids=[landmark.id]),
    )

    assert [day.day_number for day in itinerary.days] == list(range(1, 9))


def test_planner_builds_a_confirmed_itinerary_and_calculates_total_budget(db_session):
    landmark = create_landmark(db_session, landmark_name="已确认地标", city_name="开封市")
    member = create_member(db_session, MembershipTier.PREMIUM)

    itinerary = ItineraryPlannerService(db_session).create(
        member.id,
        _request(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            must_visit_landmark_ids=[landmark.id],
            confirmed_plan=True,
            confirmed_lodgings=[{"city": "开封市", "name": "已确认酒店", "nightly_price": 200}],
            landmark_costs=[{"landmark_id": landmark.id, "price": 80}],
            confirmed_items=[{"city": "开封市", "name": "已确认餐饮", "item_type": "food", "price": 35}],
            confirmed_transports=[{"leg_label": "去程", "departure": "郑州", "arrival": "开封市", "travel_date": date(2026, 9, 1), "mode": "train", "option_id": "G100", "price": 50}],
        ),
    )

    assert itinerary.generator_version == "confirmed-itinerary-v1"
    assert itinerary.budget_summary["estimated_amount"] == 365
    assert itinerary.days[0].travel_context["confirmed_food_events"][0]["name"] == "已确认餐饮"


def test_confirmed_choices_are_scheduled_once_with_times_and_costs(db_session):
    landmark = create_landmark(db_session, landmark_name="开封府", city_name="开封市")
    member = create_member(db_session, MembershipTier.PREMIUM)

    itinerary = ItineraryPlannerService(db_session).create(
        member.id,
        _request(
            must_visit_landmark_ids=[landmark.id],
            traveler_count=2,
            confirmed_plan=True,
            confirmed_lodgings=[{"city": "开封市", "name": "酒店", "nightly_price": 200}],
            landmark_costs=[{"landmark_id": landmark.id, "price": 80}],
            confirmed_items=[
                {"city": "开封市", "name": "清明上河园", "item_type": "scenic", "price": 120},
                {"city": "开封市", "name": "灌汤包", "item_type": "food", "price": 60},
            ],
        ),
    )

    supplementals = [item for day in itinerary.days for item in day.supplemental_items]
    foods = [item for day in itinerary.days for item in day.travel_context["confirmed_food_events"]]
    assert [item["name"] for item in supplementals] == ["清明上河园"]
    assert supplementals[0]["time_slot"] == "11:00"
    assert supplementals[0]["price"] == 240
    assert [item["name"] for item in foods] == ["灌汤包"]
    assert itinerary.budget_summary["estimated_amount"] == 660


def test_planner_separates_required_landmarks_in_different_cities(db_session):
    first = create_landmark(db_session, landmark_name="广州地标", city_name="广州", province_name="广东")
    second = create_landmark(db_session, landmark_name="珠海地标", city_name="珠海", province_name="广东")
    member = create_member(db_session, MembershipTier.PREMIUM)

    itinerary = ItineraryPlannerService(db_session).create(
        member.id,
        _request(
            end_date=date(2026, 9, 2),
            must_visit_landmark_ids=[first.id, second.id],
        ),
    )

    cities = [day.travel_context["city"] for day in itinerary.days]
    assert cities == ["广州", "珠海"]
    assert itinerary.days[1].travel_context["intercity_transport"][0]["label"] == "城市间移动"


def test_city_skeleton_is_built_before_external_queries_and_has_city_specific_nights(db_session):
    first = create_landmark(db_session, landmark_name="忻州地标", city_name="忻州市", province_name="山西")
    second = create_landmark(db_session, landmark_name="朔州地标", city_name="朔州市", province_name="山西")
    third = create_landmark(db_session, landmark_name="临汾地标", city_name="临汾市", province_name="山西")

    city_plan = ItineraryPlannerService(db_session)._city_plan(
        [first, second, third], [first.id, second.id, third.id], date(2026, 9, 1), 8
    )

    assert city_plan == [
        {"city": "忻州市", "start_date": date(2026, 9, 1), "days": 3, "nights": 3},
        {"city": "朔州市", "start_date": date(2026, 9, 4), "days": 3, "nights": 3},
        {"city": "临汾市", "start_date": date(2026, 9, 7), "days": 2, "nights": 1},
    ]


def test_planner_rejects_an_overseas_required_landmark(db_session):
    overseas = create_landmark(
        db_session, landmark_name="海外地标", country_code="US", country_name="美国", city_name="纽约"
    )
    member = create_member(db_session, MembershipTier.PREMIUM)

    with pytest.raises(ItineraryValidationError, match="domestic landmarks"):
        ItineraryPlannerService(db_session).create(member.id, _request(must_visit_landmark_ids=[overseas.id]))
