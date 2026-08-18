from datetime import date

from app.core.auth import create_access_token
from app.models.enums import IPType, MembershipTier
from tests.factories import create_landmark, create_member


def _headers(member) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(member.id)}"}


def test_mvp_journey_covers_three_ip_types_and_member_services(client, db_session):
    literature = create_landmark(db_session, work_title="边城", landmark_name="茶峒古镇", ip_type=IPType.LITERATURE)
    game = create_landmark(db_session, work_title="黑神话：悟空", landmark_name="应县木塔", ip_type=IPType.GAME)
    screen = create_landmark(db_session, work_title="狂飙", landmark_name="江门骑楼", ip_type=IPType.SCREEN)
    free = create_member(db_session, MembershipTier.FREE)
    lite = create_member(db_session, MembershipTier.LITE)
    premium = create_member(db_session, MembershipTier.PREMIUM)

    for ip_type, landmark_id in (("literature", literature.id), ("game", game.id), ("screen", screen.id)):
        catalog = client.get(f"/api/v1/landmarks?ip_type={ip_type}")
        assert catalog.status_code == 200
        assert [item["id"] for item in catalog.json()["items"]] == [landmark_id]

    free_map = client.get("/api/v1/maps/landmarks", headers=_headers(free))
    assert free_map.status_code == 200
    assert {marker["id"] for marker in free_map.json()["items"]} == {literature.id, game.id, screen.id}
    lite_map = client.get("/api/v1/maps/landmarks", headers=_headers(lite))
    assert lite_map.status_code == 200
    assert {marker["id"] for marker in lite_map.json()["items"]} == {literature.id, game.id, screen.id}

    created = client.post(
        "/api/v1/itineraries",
        json={
            "title": "山西游戏地标一日行程",
            "ip_type": "game",
            "country": "CN",
            "start_date": date(2026, 9, 1).isoformat(),
            "end_date": date(2026, 9, 1).isoformat(),
            "daily_hours": 8,
            "must_visit_landmark_ids": [game.id],
        },
        headers=_headers(premium),
    )
    assert created.status_code == 200
    itinerary_id = created.json()["id"]
    assert created.json()["days"][0]["stops"][0]["landmark_id"] == game.id

    assert client.get(f"/api/v1/itineraries/{itinerary_id}/exports/html", headers=_headers(premium)).status_code == 200
    assert client.get(f"/api/v1/itineraries/{itinerary_id}/exports/xlsx", headers=_headers(premium)).status_code == 200
