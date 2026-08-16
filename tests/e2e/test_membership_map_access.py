from app.core.auth import create_access_token
from app.models.enums import MembershipTier
from tests.factories import create_landmark, create_member


def test_free_browser_cannot_open_member_map_page(client, db_session):
    create_landmark(db_session)

    response = client.get("/maps/games")

    assert response.status_code == 403
    assert "39.57" not in response.text


def test_lite_browser_map_page_fetches_only_protected_api_url(client, db_session):
    create_landmark(db_session)
    member = create_member(db_session, MembershipTier.LITE)
    client.cookies.set("ip_landmark_access_token", create_access_token(member.id))

    response = client.get("/maps/games?country=CN")

    assert response.status_code == 200
    assert "/api/v1/maps/landmarks?ip_type=game&amp;country=CN" in response.text
    assert "latitude" not in response.text
