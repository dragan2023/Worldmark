def test_admin_routes_are_disabled_without_a_local_admin_token(client):
    response = client.get("/api/v1/admin/data-quality")

    assert response.status_code == 503
    assert response.json()["detail"] == "Admin API is not configured."
