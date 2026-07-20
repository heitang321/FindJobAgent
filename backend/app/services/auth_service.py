"""登录注册认证服务工具。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import base64
import hashlib
import os
import secrets

import jwt

from app.core.config import settings
from app.services.auth_repository import UserRecord, user_repository


PASSWORD_ITERATIONS = 210_000


class AuthError(ValueError):
    """登录凭证或令牌无效时抛出。"""


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return (
        f"pbkdf2_sha256${PASSWORD_ITERATIONS}$"
        f"{base64.b64encode(salt).decode()}$"
        f"{base64.b64encode(password_hash).decode()}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, expected_b64 = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(expected_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def create_access_token(user: UserRecord) -> str:
    expire_at = datetime.now(UTC) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user.id,
        "email": user.email,
        "username": user.username,
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def user_from_token(token: str) -> UserRecord:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except jwt.PyJWTError as exc:
        raise AuthError("invalid token") from exc

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise AuthError("invalid token")
    user = user_repository.get_by_id(user_id)
    if user is None:
        raise AuthError("user not found")
    return user
