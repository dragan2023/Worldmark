from app.core.auth import create_access_token
from app.core.config import Settings, get_settings
from app.models.enums import MembershipTier
from tests.factories import create_landmark, create_member


def test_anonymous_map_request_returns_only_published_geocoded_markers(client, db_session):
    visible = create_landmark(db_session, landmark_name="有坐标地点")
    create_landmark(db_session, landmark_name="无坐标地点", has_coordinates=False)
    create_landmark(db_session, landmark_name="候选地点", published=False)

    response = client.get("/api/v1/maps/landmarks?ip_type=game")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [visible.id]
    assert items[0]["latitude"] == 39.57


def test_lite_member_gets_only_published_geocoded_markers(client, db_session):
    visible = create_landmark(db_session, landmark_name="有坐标地点")
    create_landmark(db_session, landmark_name="无坐标地点", has_coordinates=False)
    create_landmark(db_session, landmark_name="候选地点", published=False)
    member = create_member(db_session, MembershipTier.LITE)

    response = client.get(
        "/api/v1/maps/landmarks?ip_type=game&country=CN",
        headers={"Authorization": f"Bearer {create_access_token(member.id)}"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [visible.id]
    assert items[0]["latitude"] == 39.57


def test_premium_member_can_open_map_html_without_coordinates_in_source(client, db_session):
    create_landmark(db_session)
    member = create_member(db_session, MembershipTier.PREMIUM)
    client.cookies.set("ip_landmark_access_token", create_access_token(member.id))

    response = client.get("/maps/games?work=悟空")

    assert response.status_code == 200
    assert "静态参考地图" in response.text
    assert "39.57" not in response.text
    assert "113.17" not in response.text


def test_map_page_reports_missing_tile_configuration(client, app, db_session):
    create_landmark(db_session)
    member = create_member(db_session, MembershipTier.LITE)
    settings = Settings(map_tile_url=None)
    app.dependency_overrides[get_settings] = lambda: settings
    client.cookies.set("ip_landmark_access_token", create_access_token(member.id, settings))

    response = client.get("/maps/games")

    assert response.status_code == 503
    assert "出错了" in response.text
