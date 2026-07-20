"""邮箱验证码存储：生产使用 MySQL，测试使用进程内实现。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from threading import Lock
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.verification_code import EmailVerificationCode
from app.schemas.auth import VerificationPurpose
from app.services.email_sender import QQEmailSender, email_sender


def _generate_code() -> str:
    length = max(4, min(settings.AUTH_VERIFICATION_CODE_LENGTH, 8))
    start = 10 ** (length - 1)
    end = (10**length) - 1
    return str(secrets.randbelow(end - start + 1) + start)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _send_code(sender: QQEmailSender, email: str, code: str) -> None:
    if not settings.AUTH_EMAIL_SEND_ENABLED:
        return
    sender.send(
        to=email,
        subject="FindJobAgent 邮箱验证码",
        content=(
            f"你的 FindJobAgent 验证码是：{code}\n\n"
            f"有效期 {settings.AUTH_VERIFICATION_EXPIRE_SECONDS // 60} 分钟。"
            "如果不是你本人操作，请忽略这封邮件。"
        ),
    )


class MySQLVerificationCodeManager:
    def __init__(self, sender: QQEmailSender) -> None:
        self._sender = sender

    def issue(self, *, email: str, purpose: VerificationPurpose) -> str:
        code = _generate_code()
        record = EmailVerificationCode(
            id=uuid4().hex,
            user_id=None,
            email=email.casefold(),
            purpose=purpose,
            code_hash=_hash_code(code),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.AUTH_VERIFICATION_EXPIRE_SECONDS),
            used_at=None,
            send_count=1,
        )
        with SessionLocal() as database:
            database.add(record)
            database.commit()
        _send_code(self._sender, email, code)
        return code

    def verify(
        self,
        *,
        email: str,
        purpose: VerificationPurpose,
        code: str,
    ) -> bool:
        now = datetime.now(UTC)
        with SessionLocal() as database:
            statement = (
                select(EmailVerificationCode)
                .where(
                    EmailVerificationCode.email == email.casefold(),
                    EmailVerificationCode.purpose == purpose,
                    EmailVerificationCode.used_at.is_(None),
                )
                .order_by(EmailVerificationCode.created_at.desc())
                .limit(1)
            )
            record = database.execute(statement).scalar_one_or_none()
            if record is None:
                return False
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at < now:
                return False
            if not secrets.compare_digest(record.code_hash, _hash_code(code)):
                return False
            record.used_at = now
            database.commit()
            return True

    def clear(self) -> None:
        with SessionLocal() as database:
            database.query(EmailVerificationCode).delete()
            database.commit()


@dataclass(slots=True)
class VerificationCodeRecord:
    code_hash: str
    expires_at: datetime


class InMemoryVerificationCodeManager:
    def __init__(self, sender: QQEmailSender) -> None:
        self._sender = sender
        self._records: dict[
            tuple[str, VerificationPurpose],
            VerificationCodeRecord,
        ] = {}
        self._lock = Lock()

    def issue(self, *, email: str, purpose: VerificationPurpose) -> str:
        code = _generate_code()
        key = (email.casefold(), purpose)
        with self._lock:
            self._records[key] = VerificationCodeRecord(
                code_hash=_hash_code(code),
                expires_at=datetime.now(UTC)
                + timedelta(seconds=settings.AUTH_VERIFICATION_EXPIRE_SECONDS),
            )
        _send_code(self._sender, email, code)
        return code

    def verify(
        self,
        *,
        email: str,
        purpose: VerificationPurpose,
        code: str,
    ) -> bool:
        key = (email.casefold(), purpose)
        with self._lock:
            record = self._records.get(key)
            if record is None:
                return False
            if record.expires_at < datetime.now(UTC):
                self._records.pop(key, None)
                return False
            if not secrets.compare_digest(record.code_hash, _hash_code(code)):
                return False
            self._records.pop(key, None)
            return True

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


verification_code_manager = (
    InMemoryVerificationCodeManager(email_sender)
    if settings.TESTING
    else MySQLVerificationCodeManager(email_sender)
)
