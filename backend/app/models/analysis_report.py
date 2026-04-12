"""
AnalysisReport ORM 模型
对应 MySQL analysis_reports 表
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import Integer, BigInteger, Text, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.product import Product
    from app.models.conversation import Conversation
    from app.models.analysis_task import AnalysisTask

from app.models import Base


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    analysis_task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)        # AI 生成的文本总结
    statistics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    charts_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # ECharts JSON 配置
    evidence_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 关联关系
    analysis_task: Mapped["AnalysisTask"] = relationship(back_populates="report")
    user: Mapped["User"] = relationship(back_populates="analysis_reports")
    product: Mapped["Product"] = relationship(back_populates="analysis_reports")
    conversation: Mapped["Conversation"] = relationship(back_populates="analysis_reports")

    def __repr__(self) -> str:
        return f"<AnalysisReport id={self.id} product_id={self.product_id}>"
