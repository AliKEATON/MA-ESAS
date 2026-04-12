"""
Product ORM 模型
对应 MySQL products 表
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, BigInteger, Enum, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.conversation import Conversation
    from app.models.analysis_task import AnalysisTask
    from app.models.analysis_report import AnalysisReport

from app.models import Base


class ProductStatus(str, enum.Enum):
    PENDING = "pending"       # 等待爬取
    CRAWLING = "crawling"     # 爬取中
    COMPLETED = "completed"   # 爬取完成
    FAILED = "failed"         # 爬取失败


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # jd/taobao/tmall
    external_product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_url: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    crawl_status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, name="productstatus"),
        default=ProductStatus.PENDING,
        nullable=False,
        index=True,
    )
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_crawl_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 关联关系
    comments: Mapped[list["Comment"]] = relationship(back_populates="product")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="product")
    analysis_tasks: Mapped[list["AnalysisTask"]] = relationship(back_populates="product")
    analysis_reports: Mapped[list["AnalysisReport"]] = relationship(back_populates="product")

    def __repr__(self) -> str:
        return f"<Product id={self.id} crawl_status={self.crawl_status} url={self.product_url[:50]}>"
