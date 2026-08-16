import json
from datetime import date

import httpx
import pytest

from app.integrations.deepseek_client import DeepSeekClient
from app.services.deepseek_itinerary_generator import DeepSeekItineraryGenerator, ItineraryGenerationError
from tests.factories import create_landmark


def _generator(payload) -> DeepSeekItineraryGenerator:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]})

    return DeepSeekItineraryGenerator(DeepSeekClient("test-key", transport=httpx.MockTransport(handler)))


def test_generator_parses_days_and_honors_required_stop(db_session):
    first = create_landmark(db_session, landmark_name="必去地标")
    second = create_landmark(db_session, landmark_name="普通地标")
    candidates = [first, second]

    payload = {
        "days": [
            {"day_number": 1, "summary": "第一天", "stops": [
                {"landmark_id": first.id, "time_slot": "09:00", "planned_minutes": 90, "selection_reason": "IP 原型地标，必打卡。"}
            ]},
            {"day_number": 2, "summary": "第二天", "stops": [
                {"landmark_id": second.id, "time_slot": "09:00", "planned_minutes": 60, "selection_reason": "顺路补充。"}
            ]},
        ]
    }

    days = _generator(payload).generate(candidates, [first.id], date(2026, 9, 1), 2, 8)

    assert len(days) == 2
    assert days[0].stops[0].landmark_id == first.id
    assert days[0].stops[0].planned_minutes == 90
    assert days[1].itinerary_date == date(2026, 9, 2)


def test_generator_serializes_date_values_in_external_planning_context(db_session):
    landmark = create_landmark(db_session, landmark_name="地标")
    payload = {"days": [{"day_number": 1, "stops": [{"landmark_id": landmark.id, "planned_minutes": 60}]}]}

    days = _generator(payload).generate(
        [landmark],
        [landmark.id],
        date(2026, 9, 1),
        1,
        8,
        planning_context={"city_plan": [{"city": "开封市", "start_date": date(2026, 9, 1)}]},
    )

    assert days[0].stops[0].landmark_id == landmark.id


def test_generator_rejects_unknown_landmark(db_session):
    landmark = create_landmark(db_session, landmark_name="地标")
    payload = {"days": [{"day_number": 1, "stops": [{"landmark_id": 99999, "planned_minutes": 60}]}]}

    with pytest.raises(ItineraryGenerationError, match="unknown"):
        _generator(payload).generate([landmark], [], date(2026, 9, 1), 1, 8)


def test_generator_rejects_omitted_required_stop(db_session):
    first = create_landmark(db_session, landmark_name="必去")
    second = create_landmark(db_session, landmark_name="其他")
    payload = {"days": [{"day_number": 1, "stops": [{"landmark_id": second.id, "planned_minutes": 60}]}]}

    with pytest.raises(ItineraryGenerationError, match="omitted"):
        _generator(payload).generate([first, second], [first.id], date(2026, 9, 1), 1, 8)


def test_generator_preserves_positive_planned_minutes_without_an_arbitrary_cap(db_session):
    landmark = create_landmark(db_session, landmark_name="地标")
    payload = {"days": [{"day_number": 1, "stops": [{"landmark_id": landmark.id, "planned_minutes": 9999}]}]}

    days = _generator(payload).generate([landmark], [], date(2026, 9, 1), 1, 8)

    assert days[0].stops[0].planned_minutes == 9999
