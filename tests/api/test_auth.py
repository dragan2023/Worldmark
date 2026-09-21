"""认证 API：注册 / 登录 / 登出 / me / 封禁即时生效。"""

from app.models.enums import MembershipTier, UserRole
from tests.factories import create_member


def test_register_creates_level2_user_with_free_membership(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "newbie", "email": "new@example.org", "password": "password123"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["authenticated"] is True
    assert body["username"] == "newbie"
    assert body["email"] == "new@example.org"
    assert body["role"] == UserRole.LEVEL2.value
    assert body["tier"] == MembershipTier.FREE.value
    assert body["permissions"]["can_intake"] is True
    assert body["permissions"]["can_generate_itinerary"] is False
    assert "ip_landmark_access_token" in response.cookies


def test_register_rejects_duplicate_email(client):
    payload = {"username": "first", "email": "dup@example.org", "password": "password123"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    dup_email = dict(payload, username="second")
    assert client.post("/api/v1/auth/register", json=dup_email).status_code == 409


def test_register_rejects_duplicate_username_and_bad_username(client):
    base = {"username": "sameuser", "email": "a@example.org", "password": "password123"}
    assert client.post("/api/v1/auth/register", json=base).status_code == 201
    dup_name = dict(base, email="b@example.org")
    assert client.post("/api/v1/auth/register", json=dup_name).status_code == 409
    bad_name = dict(base, username="非法名", email="c@example.org")
    assert client.post("/api/v1/auth/register", json=bad_name).status_code == 422


def test_register_rejects_bad_email_and_weak_password(client):
    assert client.post(
        "/api/v1/auth/register",
        json={"username": "okname", "email": "not-an-email", "password": "password123"},
    ).status_code == 422
    assert client.post(
        "/api/v1/auth/register",
        json={"username": "okname", "email": "ok@example.org", "password": "short"},
    ).status_code == 422


def test_login_success_and_me(client):
    client.post(
        "/api/v1/auth/register",
        json={"username": "meuser", "email": "me@example.org", "password": "password123"},
    )
    logout = client.post("/api/v1/auth/logout")
    assert logout.json()["ok"] is True

    login = client.post("/api/v1/auth/login", json={"username": "meuser", "password": "password123"})
    assert login.status_code == 200
    assert login.json()["role"] == UserRole.LEVEL2.value
    assert login.json()["username"] == "meuser"

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["authenticated"] is True
    assert body["username"] == "meuser"
    assert body["permissions"]["can_intake"] is True


def test_login_rejects_wrong_password(client):
    client.post(
        "/api/v1/auth/register",
        json={"username": "pwuser", "email": "pw@example.org", "password": "password123"},
    )
    client.post("/api/v1/auth/logout")
    failed = client.post("/api/v1/auth/login", json={"username": "pwuser", "password": "wrong-password"})
    assert failed.status_code == 401


def test_banned_user_cannot_login_and_token_is_rejected(client, db_session):
    registered = client.post(
        "/api/v1/auth/register",
        json={"username": "banuser", "email": "ban@example.org", "password": "password123"},
    )
    token = registered.json()["token"]
    from app.models.user import User

    user = db_session.query(User).filter(User.username == "banuser").one()
    user.status = "banned"
    db_session.commit()

    client.post("/api/v1/auth/logout")
    assert client.post("/api/v1/auth/login", json={"username": "banuser", "password": "password123"}).status_code == 403

    # 已签发的 token 也立即失效
    rejected = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert rejected.status_code == 403


def test_me_anonymous_returns_unauthenticated(client):
    body = client.get("/api/v1/auth/me").json()
    assert body["authenticated"] is False
    assert body["role"] == "anonymous"


def test_login_page_and_register_page_render(client):
    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200


def test_admin_role_member_via_factory(client, db_session):
    create_member(db_session, MembershipTier.FREE, role=UserRole.ADMIN.value)
    db_session.commit()
    from app.core.auth import create_access_token
    from app.models.user import User

    user = db_session.query(User).filter(User.role == UserRole.ADMIN.value).first()
    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {create_access_token(user.id)}"}
    )
    assert me.json()["role"] == UserRole.ADMIN.value
    assert me.json()["permissions"]["can_manage_users"] is True
