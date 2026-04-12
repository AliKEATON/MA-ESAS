"""
商品相关 Pydantic Schema
仅供内部使用（爬虫服务、分析服务）
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum


class ProductStatus(str, Enum):
    """商品爬取状态"""
    PENDING = "pending"
    CRAWLING = "crawling"
    COMPLETED = "completed"
    FAILED = "failed"


# ========== 内部响应 Schema ==========

class ProductStatusResponse(BaseModel):
    """商品状态响应（内部使用）"""
    id: int
    product_name: Optional[str]
    crawl_status: ProductStatus
    comment_count: int
    last_crawled_at: Optional[datetime]

    class Config:
        from_attributes = True
