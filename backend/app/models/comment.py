"""
Comment ORM 模型
对应 MySQL comments 表
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Integer, BigInteger, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.product import Product

from app.models import Base


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint("product_id", "source_comment_id", name="uq_product_source_comment"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 1-5
    dimension: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    dimension_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_comment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_vectorized: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 关联关系
    product: Mapped["Product"] = relationship(back_populates="comments")

    def __repr__(self) -> str:
        return f"<Comment id={self.id} product_id={self.product_id} score={self.score}>"
