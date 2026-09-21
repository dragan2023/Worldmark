def test_admin_routes_require_privileges_without_a_local_admin_token(client):
    """未配置静态令牌且未以管理员身份登录时，管理接口一律 401。"""
    response = client.get("/api/v1/admin/data-quality")

    assert response.status_code == 401
    assert response.json()["detail"] == "需要管理员权限。"
