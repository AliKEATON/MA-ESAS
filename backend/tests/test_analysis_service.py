from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Product
from app.models.product import ProductStatus
from app.services.analysis_service import AnalysisService


def test_should_crawl_handles_recent_naive_datetime() -> None:
    """最近抓取的无时区时间不应触发时区计算异常，也不应重复抓取。"""
    product = Product(
        source="jd",
        external_product_id="crawl-1001",
        product_url="https://item.jd.com/crawl-1001.html",
        crawl_status=ProductStatus.COMPLETED,
        last_crawled_at=datetime.utcnow() - timedelta(hours=6),
    )

    assert AnalysisService._should_crawl(product) is False


def test_should_crawl_allows_stale_aware_datetime() -> None:
    """超过阈值的有时区时间应继续触发重新抓取。"""
    product = Product(
        source="jd",
        external_product_id="crawl-1002",
        product_url="https://item.jd.com/crawl-1002.html",
        crawl_status=ProductStatus.COMPLETED,
        last_crawled_at=datetime.now(timezone.utc) - timedelta(days=5),
    )

    assert AnalysisService._should_crawl(product) is True
