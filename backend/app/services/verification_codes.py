"""MySQL 版邮箱验证码管理器。

验证码存储在 email_verification_codes 表中，支持：
- 发送验证码（issue）
- 校验验证码（verify）
- 清理过期记录
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from uuid import uuid4

from sqlalchemy import select, update

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.verification_code import EmailVerificationCode
from app.schemas.auth import VerificationPurpose
from app.services.email_sender import QQEmailSender, email_sender


class VerificationCodeManager:
    """基于 MySQL 的验证码管理器。"""

    def __init__(self, sender: QQEmailSender) -> None:
        self._sender = sender

    def issue(self, *, email: str, purpose: VerificationPurpose) -> str:
        """生成验证码，存入数据库，并发送邮件。"""
        code = self._generate_code()
        code_hash = self._hash_code(code)
        expires_at = datetime.now(UTC) + timedelta(
            seconds=settings.AUTH_VERIFICATION_EXPIRE_SECONDS
        )

        with SessionLocal() as db:
            record = EmailVerificationCode(
                id=uuid4().hex,
                user_id=None,  # 注册时用户尚未创建
                email=email.casefold(),
                purpose=purpose,
                code_hash=code_hash,
                expires_at=expires_at,
                used_at=None,
                send_count=1,
            )
            db.add(record)
            db.commit()

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
        """校验验证码：匹配且未过期则标记已使用并返回 True。"""
        email_key = email.casefold()
        code_hash = self._hash_code(code)
        now = datetime.now(UTC)

        with SessionLocal() as db:
            stmt = (
                select(EmailVerificationCode)
                .where(
                    EmailVerificationCode.email == email_key,
                    EmailVerificationCode.purpose == purpose,
                    EmailVerificationCode.used_at.is_(None),
                )
                .order_by(EmailVerificationCode.created_at.desc())
                .limit(1)
            )
            record = db.execute(stmt).scalar_one_or_none()

            if record is None:
                return False
            if record.expires_at.replace(tzinfo=UTC) < now:
                return False
            if not secrets.compare_digest(record.code_hash, code_hash):
                return False

            # 标记已使用
            record.used_at = now
            db.commit()
            return True

    def clear(self) -> None:
        """清理所有验证码记录（测试用）。"""
        with SessionLocal() as db:
            db.query(EmailVerificationCode).delete()
            db.commit()

    def _generate_code(self) -> str:
        length = max(4, min(settings.AUTH_VERIFICATION_CODE_LENGTH, 8))
        start = 10 ** (length - 1)
        end = (10**length) - 1
        return str(secrets.randbelow(end - start + 1) + start)

    def _hash_code(self, code: str) -> str:
        return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


verification_code_manager = VerificationCodeManager(email_sender)
