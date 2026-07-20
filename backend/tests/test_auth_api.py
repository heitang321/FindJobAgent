"""登录注册认证接口测试。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.router import api_router
from app.core.config import settings
from app.services.auth_repository import user_repository
from app.services.verification_codes import verification_code_manager


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    return TestClient(app)


class TestAuthApi:
    def setup_method(self):
        user_repository.clear()
        verification_code_manager.clear()
        settings.AUTH_EMAIL_SEND_ENABLED = False
        settings.AUTH_DEBUG_RETURN_CODE = True

    def teardown_method(self):
        settings.AUTH_EMAIL_SEND_ENABLED = True
        settings.AUTH_DEBUG_RETURN_CODE = False

    def test_register_login_and_me_flow(self):
        client = _client()

        code_response = client.post(
            "/api/v1/auth/send-code",
            json={"email": "dev@example.com", "purpose": "register"},
        )
        assert code_response.status_code == 200
        assert code_response.json()["resend_after_seconds"] == 60
        register_code = code_response.json()["debug_code"]

        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": "dev@example.com",
                "username": "开发者",
                "password": "secret123",
                "confirm_password": "secret123",
                "verification_code": register_code,
            },
        )

        assert register.status_code == 200
        token = register.json()["access_token"]
        assert register.json()["user"]["email"] == "dev@example.com"

        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 200
        assert me.json()["username"] == "开发者"

        login_code = client.post(
            "/api/v1/auth/send-code",
            json={"email": "dev@example.com", "purpose": "login"},
        ).json()["debug_code"]
        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "dev@example.com",
                "password": "secret123",
                "verification_code": login_code,
            },
        )

        assert login.status_code == 200
        assert login.json()["token_type"] == "bearer"

    def test_register_requires_valid_code(self):
        client = _client()

        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "dev@example.com",
                "username": "开发者",
                "password": "secret123",
                "confirm_password": "secret123",
                "verification_code": "000000",
            },
        )

        assert response.status_code == 400
        assert "验证码" in response.json()["detail"]

    def test_register_requires_matching_passwords(self):
        client = _client()

        code = client.post(
            "/api/v1/auth/send-code",
            json={"email": "dev@example.com", "purpose": "register"},
        ).json()["debug_code"]

        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "dev@example.com",
                "username": "开发者",
                "password": "secret123",
                "confirm_password": "different123",
                "verification_code": code,
            },
        )

        assert response.status_code == 400
        assert "密码不一致" in response.json()["detail"]

    def test_register_existing_email_returns_conflict(self):
        client = _client()

        first_code = client.post(
            "/api/v1/auth/send-code",
            json={"email": "dev@example.com", "purpose": "register"},
        ).json()["debug_code"]
        first = client.post(
            "/api/v1/auth/register",
            json={
                "email": "dev@example.com",
                "username": "开发者",
                "password": "secret123",
                "confirm_password": "secret123",
                "verification_code": first_code,
            },
        )
        assert first.status_code == 200

        duplicate = client.post(
            "/api/v1/auth/register",
            json={
                "email": "dev@example.com",
                "username": "开发者",
                "password": "secret123",
                "confirm_password": "secret123",
                "verification_code": first_code,
            },
        )

        assert duplicate.status_code == 409
        assert "已注册" in duplicate.json()["detail"]

    def test_me_requires_token(self):
        response = _client().get("/api/v1/auth/me")

        assert response.status_code == 401
