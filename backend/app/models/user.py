"""
User ORM 模型
对应 MySQL users 表
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.analysis_task import AnalysisTask
    from app.models.analysis_report import AnalysisReport

from app.models import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # 关联关系（使用字符串延迟引用避免循环导入）
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")
    analysis_tasks: Mapped[list["AnalysisTask"]] = relationship(back_populates="user")
    analysis_reports: Mapped[list["AnalysisReport"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username}>"
