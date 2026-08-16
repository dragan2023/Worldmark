def test_ip_type_metadata(client):
    response = client.get("/api/v1/meta/ip-types")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"code": "literature", "name": "文学地标"},
            {"code": "game", "name": "游戏地标"},
            {"code": "screen", "name": "影视地标"},
        ]
    }
