"""登录注册用户仓库实现。

API 层依赖用户仓库接口。当前实现使用本地 JSON 文件便于开发测试，
后续可以替换为数据库实现，而不需要修改认证路由。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import threading
from typing import Protocol
from uuid import uuid4

from app.core.config import BACKEND_ROOT, settings


@dataclass(slots=True)
class UserRecord:
    id: str
    email: str
    username: str
    password_hash: str
    created_at: str

    def public_dict(self) -> dict:
        return {"id": self.id, "email": self.email, "username": self.username}


class UserRepository(Protocol):
    def get_by_email(self, email: str) -> UserRecord | None: ...

    def get_by_id(self, user_id: str) -> UserRecord | None: ...

    def create_user(
        self, *, email: str, username: str, password_hash: str
    ) -> UserRecord: ...


class LocalJsonUserRepository:
    """无数据库开发阶段使用的本地用户存储。"""

    def __init__(self, path: Path | None = None) -> None:
        configured_path = Path(settings.AUTH_LOCAL_USER_STORE)
        self.path = path or (
            configured_path
            if configured_path.is_absolute()
            else BACKEND_ROOT / configured_path
        )
        self._lock = threading.Lock()

    def get_by_email(self, email: str) -> UserRecord | None:
        email_key = email.casefold()
        with self._lock:
            for item in self._read_all():
                if item.email.casefold() == email_key:
                    return item
        return None

    def get_by_id(self, user_id: str) -> UserRecord | None:
        with self._lock:
            for item in self._read_all():
                if item.id == user_id:
                    return item
        return None

    def create_user(
        self, *, email: str, username: str, password_hash: str
    ) -> UserRecord:
        email_key = email.casefold()
        with self._lock:
            users = self._read_all()
            if any(item.email.casefold() == email_key for item in users):
                raise ValueError("email already registered")
            user = UserRecord(
                id=uuid4().hex,
                email=email_key,
                username=username.strip(),
                password_hash=password_hash,
                created_at=datetime.now(UTC).isoformat(),
            )
            users.append(user)
            self._write_all(users)
            return user

    def clear(self) -> None:
        with self._lock:
            self._write_all([])

    def _read_all(self) -> list[UserRecord]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        return [UserRecord(**item) for item in data]

    def _write_all(self, users: list[UserRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(user) for user in users]
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class DatabaseUserRepository:
    """后续数据库用户仓库占位实现。

    项目接入真实用户表后，可以在这里注入 AsyncSession 或用户服务对象。
    路由层的接口契约不需要随之变化。
    """

    def get_by_email(self, email: str) -> UserRecord | None:
        raise NotImplementedError

    def get_by_id(self, user_id: str) -> UserRecord | None:
        raise NotImplementedError

    def create_user(
        self, *, email: str, username: str, password_hash: str
    ) -> UserRecord:
        raise NotImplementedError


user_repository = LocalJsonUserRepository()
