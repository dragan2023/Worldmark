from tests.factories import create_landmark


def test_landmarks_api_filters_published_records_and_keeps_coordinates_private(client, db_session):
    visible = create_landmark(db_session)
    create_landmark(db_session, work_title="未发布", landmark_name="候选地点", published=False)

    response = client.get("/api/v1/landmarks", params={"ip_type": "game", "work": "悟空", "country": "CN"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == visible.id
    assert "latitude" not in payload["items"][0]
    assert "longitude" not in payload["items"][0]


def test_landmark_detail_returns_address_transit_and_sources(client, db_session):
    landmark = create_landmark(db_session)

    response = client.get(f"/api/v1/landmarks/{landmark.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["normalized_address"]
    assert payload["transit_text"]
    assert payload["sources"][0]["url"].startswith("https://")
    assert "latitude" not in payload


def test_landmark_picker_query_is_fuzzy_and_can_be_limited_to_domestic_records(client, db_session):
    domestic = create_landmark(db_session, work_title="开封故事", aliases="汴梁传奇", landmark_name="开封府")
    create_landmark(
        db_session,
        work_title="海外故事",
        aliases="海外别名",
        landmark_name="海外地标",
        country_code="US",
        country_name="美国",
    )

    by_landmark = client.get("/api/v1/landmarks", params={"q": "开封府", "country": "CN"})
    by_alias = client.get("/api/v1/landmarks", params={"q": "汴梁", "country": "CN"})

    assert [item["id"] for item in by_landmark.json()["items"]] == [domestic.id]
    assert [item["id"] for item in by_alias.json()["items"]] == [domestic.id]
