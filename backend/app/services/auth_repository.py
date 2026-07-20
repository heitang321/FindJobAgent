"""用户仓库：生产使用 MySQL，测试使用进程内实现。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User


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
        self,
        *,
        email: str,
        username: str,
        password_hash: str,
    ) -> UserRecord: ...


def _orm_to_record(user: User) -> UserRecord:
    return UserRecord(
        id=user.id,
        email=user.email,
        username=user.username,
        password_hash=user.password_hash,
        created_at=str(user.created_at) if user.created_at else "",
    )


class MySQLUserRepository:
    """生产环境的用户持久化。"""

    def get_by_email(self, email: str) -> UserRecord | None:
        with SessionLocal() as database:
            statement = select(User).where(User.email == email.casefold())
            user = database.execute(statement).scalar_one_or_none()
            return _orm_to_record(user) if user is not None else None

    def get_by_id(self, user_id: str) -> UserRecord | None:
        with SessionLocal() as database:
            user = database.get(User, user_id)
            return _orm_to_record(user) if user is not None else None

    def create_user(
        self,
        *,
        email: str,
        username: str,
        password_hash: str,
    ) -> UserRecord:
        email_key = email.casefold()
        with SessionLocal() as database:
            existing = database.execute(
                select(User).where(User.email == email_key)
            ).scalar_one_or_none()
            if existing is not None:
                raise ValueError("email already registered")

            user = User(
                id=uuid4().hex,
                email=email_key,
                username=username.strip(),
                password_hash=password_hash,
            )
            database.add(user)
            database.commit()
            database.refresh(user)
            return _orm_to_record(user)


class InMemoryUserRepository:
    """不访问外部数据库的测试实现。"""

    def __init__(self) -> None:
        self._users: dict[str, UserRecord] = {}
        self._lock = Lock()

    def get_by_email(self, email: str) -> UserRecord | None:
        email_key = email.casefold()
        with self._lock:
            return next(
                (
                    user
                    for user in self._users.values()
                    if user.email.casefold() == email_key
                ),
                None,
            )

    def get_by_id(self, user_id: str) -> UserRecord | None:
        with self._lock:
            return self._users.get(user_id)

    def create_user(
        self,
        *,
        email: str,
        username: str,
        password_hash: str,
    ) -> UserRecord:
        email_key = email.casefold()
        with self._lock:
            if any(user.email == email_key for user in self._users.values()):
                raise ValueError("email already registered")
            user = UserRecord(
                id=uuid4().hex,
                email=email_key,
                username=username.strip(),
                password_hash=password_hash,
                created_at=datetime.now(UTC).isoformat(),
            )
            self._users[user.id] = user
            return user

    def clear(self) -> None:
        with self._lock:
            self._users.clear()


user_repository: UserRepository = (
    InMemoryUserRepository() if settings.TESTING else MySQLUserRepository()
)
