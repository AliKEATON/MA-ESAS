"""
Conversation 和 Message ORM 模型
对应 MySQL conversations 表与 messages 表
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Integer, BigInteger, Enum, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.product import Product
    from app.models.analysis_task import AnalysisTask
    from app.models.analysis_report import AnalysisReport

from app.models import Base


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageType(str, enum.Enum):
    CHAT = "chat"
    ANALYSIS_REQUEST = "analysis_request"
    ANALYSIS_RESULT = "analysis_result"
    SYSTEM_NOTICE = "system_notice"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bound_product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # 关联关系
    user: Mapped["User"] = relationship(back_populates="conversations")
    product: Mapped["Product"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    analysis_tasks: Mapped[list["AnalysisTask"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    analysis_reports: Mapped[list["AnalysisReport"]] = relationship(
        back_populates="conversation"
    )

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} user_id={self.user_id} title={self.title}>"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="messagerole"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[MessageType] = mapped_column(
        Enum(MessageType, name="messagetype"),
        nullable=False,
        default=MessageType.CHAT,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 关联关系
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    triggered_analysis_task: Mapped["AnalysisTask | None"] = relationship(
        back_populates="trigger_message", uselist=False
    )

    def __repr__(self) -> str:
        return (
            f"<Message id={self.id} role={self.role} "
            f"message_type={self.message_type} conversation_id={self.conversation_id}>"
        )
