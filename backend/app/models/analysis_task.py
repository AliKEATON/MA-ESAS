"""
AnalysisTask ORM 模型
对应 MySQL analysis_tasks 表
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, BigInteger, Enum, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.product import Product
    from app.models.conversation import Conversation, Message
    from app.models.analysis_report import AnalysisReport


class AnalysisTaskStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger_message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[AnalysisTaskStatus] = mapped_column(
        Enum(AnalysisTaskStatus, name="analysistaskstatus"),
        default=AnalysisTaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    current_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 关联关系
    user: Mapped["User"] = relationship(back_populates="analysis_tasks")
    product: Mapped["Product"] = relationship(back_populates="analysis_tasks")
    conversation: Mapped["Conversation"] = relationship(back_populates="analysis_tasks")
    trigger_message: Mapped["Message"] = relationship(back_populates="triggered_analysis_task")
    report: Mapped["AnalysisReport | None"] = relationship(back_populates="analysis_task", uselist=False)

    def __repr__(self) -> str:
        return f"<AnalysisTask id={self.id} task_id={self.task_id} status={self.status}>"
