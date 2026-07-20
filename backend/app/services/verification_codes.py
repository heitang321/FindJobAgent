"""内存版邮箱验证码管理器。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
import threading

from app.core.config import settings
from app.schemas.auth import VerificationPurpose
from app.services.email_sender import QQEmailSender, email_sender


@dataclass(slots=True)
class VerificationCodeRecord:
    code_hash: str
    expires_at: datetime


class VerificationCodeManager:
    def __init__(self, sender: QQEmailSender) -> None:
        self._sender = sender
        self._records: dict[tuple[str, VerificationPurpose], VerificationCodeRecord] = {}
        self._lock = threading.Lock()

    def issue(self, *, email: str, purpose: VerificationPurpose) -> str:
        code = self._generate_code()
        key = self._key(email, purpose)
        expires_at = datetime.now(UTC) + timedelta(
            seconds=settings.AUTH_VERIFICATION_EXPIRE_SECONDS
        )
        with self._lock:
            self._records[key] = VerificationCodeRecord(
                code_hash=self._hash_code(code),
                expires_at=expires_at,
            )

        if settings.AUTH_EMAIL_SEND_ENABLED:
            self._sender.send(
                to=email,
                subject="FindJobAgent 邮箱验证码",
                content=(
                    f"你的 FindJobAgent 验证码是：{code}\n\n"
                    f"有效期 {settings.AUTH_VERIFICATION_EXPIRE_SECONDS // 60} 分钟。"
                    "如果不是你本人操作，请忽略这封邮件。"
                ),
            )
        return code

    def verify(
        self, *, email: str, purpose: VerificationPurpose, code: str
    ) -> bool:
        key = self._key(email, purpose)
        with self._lock:
            record = self._records.get(key)
            if record is None:
                return False
            if record.expires_at < datetime.now(UTC):
                self._records.pop(key, None)
                return False
            if not secrets.compare_digest(record.code_hash, self._hash_code(code)):
                return False
            self._records.pop(key, None)
            return True

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def _generate_code(self) -> str:
        length = max(4, min(settings.AUTH_VERIFICATION_CODE_LENGTH, 8))
        start = 10 ** (length - 1)
        end = (10**length) - 1
        return str(secrets.randbelow(end - start + 1) + start)

    def _key(
        self, email: str, purpose: VerificationPurpose
    ) -> tuple[str, VerificationPurpose]:
        return (email.casefold(), purpose)

    def _hash_code(self, code: str) -> str:
        return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


verification_code_manager = VerificationCodeManager(email_sender)
