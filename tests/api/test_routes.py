from pydantic import SecretStr

from app.core.auth import create_access_token
from app.core.config import Settings, get_settings
from app.models.enums import MembershipTier
from tests.factories import create_landmark, create_member


def test_admin_creates_and_publishes_route_then_lite_member_reads_it(client, app, db_session):
    first = create_landmark(db_session, landmark_name="第一站")
    second = create_landmark(db_session, landmark_name="第二站")
    admin_settings = Settings(admin_api_token=SecretStr("route-admin"), map_tile_url="https://tiles.example/{z}/{x}/{y}.png")
    app.dependency_overrides[get_settings] = lambda: admin_settings

    created = client.post(
        "/api/v1/admin/routes",
        headers={"X-Admin-Token": "route-admin"},
        json={
            "title": "山西推荐路线",
            "summary": "人工维护的访问顺序。",
            "duration_text": "半日",
            "stops": [{"landmark_id": second.id, "stay_minutes": 45}, {"landmark_id": first.id, "stay_minutes": 30}],
        },
    )

    assert created.status_code == 200
    route_id = created.json()["id"]
    preview = client.get(f"/api/v1/admin/routes/{route_id}/preview", headers={"X-Admin-Token": "route-admin"})
    assert preview.status_code == 200
    assert preview.json()["stops"][0]["landmark_name"] == "第二站"
    published = client.post(f"/api/v1/admin/routes/{route_id}/publish", headers={"X-Admin-Token": "route-admin"})
    assert published.status_code == 200

    member = create_member(db_session, MembershipTier.LITE)
    response = client.get(
        f"/api/v1/routes/{route_id}",
        headers={"Authorization": f"Bearer {create_access_token(member.id, admin_settings)}"},
    )

    assert response.status_code == 200
    assert [stop["landmark_name"] for stop in response.json()["stops"]] == ["第二站", "第一站"]


def test_anonymous_user_can_read_published_route(client, app, db_session):
    first = create_landmark(db_session, landmark_name="第一站")
    second = create_landmark(db_session, landmark_name="第二站")
    admin_settings = Settings(admin_api_token=SecretStr("route-admin"))
    app.dependency_overrides[get_settings] = lambda: admin_settings

    created = client.post(
        "/api/v1/admin/routes",
        headers={"X-Admin-Token": "route-admin"},
        json={
            "title": "匿名可读路线",
            "summary": "人工维护的访问顺序。",
            "duration_text": "半日",
            "stops": [{"landmark_id": first.id, "stay_minutes": 30}, {"landmark_id": second.id, "stay_minutes": 45}],
        },
    )
    assert created.status_code == 200
    route_id = created.json()["id"]
    published = client.post(f"/api/v1/admin/routes/{route_id}/publish", headers={"X-Admin-Token": "route-admin"})
    assert published.status_code == 200

    response = client.get(f"/api/v1/routes/{route_id}")

    assert response.status_code == 200
    assert [stop["landmark_name"] for stop in response.json()["stops"]] == ["第一站", "第二站"]
