"""登录注册验证码邮件发送工具。"""

from __future__ import annotations

from email.header import Header
from email.mime.text import MIMEText
import smtplib

from app.core.config import settings


class EmailSendError(RuntimeError):
    """SMTP 服务商拒绝或发送邮件失败时抛出。"""


class QQEmailSender:
    """通过 QQ SMTP SSL 发送纯文本邮件。"""

    def send(self, *, to: str, subject: str, content: str) -> None:
        if not settings.EMAIL_FROM or not settings.EMAIL_PASSWORD:
            raise EmailSendError("EMAIL_FROM or EMAIL_PASSWORD is not configured")

        msg = MIMEText(content, "plain", "utf-8")
        msg["To"] = to
        msg["From"] = settings.EMAIL_FROM
        msg["Subject"] = str(Header(subject, "utf-8"))

        try:
            smtp = smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT)
            smtp.login(settings.EMAIL_FROM, settings.EMAIL_PASSWORD)
            smtp.sendmail(settings.EMAIL_FROM, to, msg.as_string())
            smtp.quit()
        except Exception as exc:  # pragma: no cover - 依赖邮件服务商和网络环境
            raise EmailSendError(str(exc)) from exc


email_sender = QQEmailSender()
