"""智能问答会话表 ORM 模型。

两张表：
- chat_sessions: 会话元信息（标题、用户归属）
- chat_messages: 消息明细（角色、内容、类型）

关系：一个 session 有多条 message（一对多）。
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, desc, select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import SessionLocal
from app.models.base import Base


class ChatSession(Base):
    """聊天会话表，主键为 VARCHAR(36) UUID。"""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, default="新对话"
    )

    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.seq",
    )

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id!r}, title={self.title!r})>"


class ChatMessage(Base):
    """聊天消息表，主键为 BIG 自增 ID。"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, comment="消息序号，从 1 开始递增")
    role: Mapped[str] = mapped_column(String(16), nullable=False, comment="user|assistant")
    content: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    msg_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="qa",
        comment="qa|chart|analysis|job_search|resume_advice|interview|salary|error"
    )
    keywords: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="岗位搜索时使用的关键词"
    )

    session: Mapped[ChatSession] = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id!r}, role={self.role!r}, type={self.msg_type!r})>"


# ===== CRUD 操作 =====

def create_session(session_id: str, user_id: str, title: str = "新对话") -> dict:
    """创建新会话，返回 dict。"""
    with SessionLocal() as db:
        session = ChatSession(id=session_id, user_id=user_id, title=title)
        db.add(session)
        db.commit()
        return {"id": session_id, "title": title}


def add_message(
    session_id: str,
    role: str,
    content: str,
    msg_type: str = "qa",
    keywords: str | None = None,
) -> dict:
    """向会话追加一条消息，返回消息 dict。"""
    with SessionLocal() as db:
        # 计算下一个序号
        existing = db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(desc(ChatMessage.seq))
            .limit(1)
        ).scalar_one_or_none()
        next_seq = (existing.seq + 1) if existing else 1

        msg = ChatMessage(
            session_id=session_id,
            seq=next_seq,
            role=role,
            content=content,
            msg_type=msg_type,
            keywords=keywords,
        )
        db.add(msg)
        db.commit()
        return {
            "id": msg.id,
            "session_id": session_id,
            "seq": next_seq,
            "role": role,
            "content": content,
            "type": msg_type,
            "keywords": keywords,
        }


def get_session_messages(session_id: str) -> list[dict]:
    """获取指定会话的所有消息，按 seq 升序返回。"""
    with SessionLocal() as db:
        msgs = db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq)
        ).scalars().all()
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "type": m.msg_type,
                "keywords": m.keywords,
            }
            for m in msgs
        ]


def list_user_sessions(user_id: str, limit: int = 50) -> list[dict]:
    """获取用户的会话列表，按创建时间倒序。"""
    with SessionLocal() as db:
        sessions = db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(desc(ChatSession.created_at))
            .limit(limit)
        ).scalars().all()
        return [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ]


def update_session_title(session_id: str, title: str) -> None:
    """更新会话标题。"""
    with SessionLocal() as db:
        session = db.get(ChatSession, session_id)
        if session:
            session.title = title[:200]
            db.commit()


def delete_session(session_id: str) -> None:
    """删除会话及其所有消息（级联删除）。"""
    with SessionLocal() as db:
        session = db.get(ChatSession, session_id)
        if session:
            db.delete(session)
            db.commit()
