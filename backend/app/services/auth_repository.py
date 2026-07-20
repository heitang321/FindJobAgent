"""登录注册用户仓库实现。

基于 MySQL 的用户存储，使用 SQLAlchemy ORM。
API 层依赖 UserRepository 接口，切换存储不需要修改认证路由。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.user import User


@dataclass(slots=True)
class UserRecord:
    """用户记录的轻量数据传输对象。"""

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


def _orm_to_record(user: User) -> UserRecord:
    """ORM 对象转 UserRecord DTO。"""
    return UserRecord(
        id=user.id,
        email=user.email,
        username=user.username,
        password_hash=user.password_hash,
        created_at=str(user.created_at) if user.created_at else "",
    )


class MySQLUserRepository:
    """基于 MySQL 的用户仓库实现。"""

    def get_by_email(self, email: str) -> UserRecord | None:
        email_key = email.casefold()
        with SessionLocal() as db:
            stmt = select(User).where(User.email == email_key)
            user = db.execute(stmt).scalar_one_or_none()
            if user is None:
                return None
            return _orm_to_record(user)

    def get_by_id(self, user_id: str) -> UserRecord | None:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if user is None:
                return None
            return _orm_to_record(user)

    def create_user(
        self, *, email: str, username: str, password_hash: str
    ) -> UserRecord:
        email_key = email.casefold()
        with SessionLocal() as db:
            # 检查邮箱是否已注册
            stmt = select(User).where(User.email == email_key)
            existing = db.execute(stmt).scalar_one_or_none()
            if existing is not None:
                raise ValueError("email already registered")

            user = User(
                id=uuid4().hex,
                email=email_key,
                username=username.strip(),
                password_hash=password_hash,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return _orm_to_record(user)


# 全局单例
user_repository = MySQLUserRepository()
