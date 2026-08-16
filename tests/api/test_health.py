def test_live_health_check(client):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_page_shows_three_modules(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "文学地标" in response.text
    assert "游戏地标" in response.text
    assert "影视地标" in response.text
