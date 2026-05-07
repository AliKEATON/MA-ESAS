"""
独立爬虫验证脚本

用途：
1. 固定抓取指定京东商品；
2. 固定抓取 15 轮评论加载；
3. 通过 CrawlerService 完成评论清洗、入库和向量化；
4. 打印商品状态和评论入库摘要，便于本地联调验证。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import SessionLocal
from app.models import Comment
from app.schemas.product import ProductStatusResponse
from app.services.analysis_service import AnalysisService
from app.services.crawler_service import CrawlerService
from app.utils.link_extractor import LinkExtractor

TARGET_URL = "https://item.jd.com/100044848690.html"
MAX_SCROLL_ROUNDS = 15


def _prepare_product(db) -> int:
    """按商品链接获取或创建商品记录，返回本地 product_id。"""
    link_info = LinkExtractor.extract_from_text(TARGET_URL)
    if not link_info:
        raise ValueError(f"无法从目标链接中解析商品信息: {TARGET_URL}")

    product = AnalysisService._get_or_create_product(db, link_info)
    db.commit()
    db.refresh(product)
    return product.id


def _print_summary(db, product_id: int, status: ProductStatusResponse) -> None:
    """打印本次爬虫验证的摘要信息。"""
    latest_comments = (
        db.query(Comment)
        .filter(Comment.product_id == product_id)
        .order_by(Comment.created_at.desc())
        .limit(5)
        .all()
    )
    vectorized_count = db.query(Comment).filter(
        Comment.product_id == product_id,
        Comment.is_vectorized.is_(True),
    ).count()

    print("PRODUCT_ID:", product_id)
    print("PRODUCT_URL:", status.product_url)
    print("PRODUCT_NAME:", status.product_name)
    print("CRAWL_STATUS:", status.crawl_status)
    print("COMMENT_COUNT:", status.comment_count)
    print("VECTORIZED_COUNT:", vectorized_count)
    print(
        "LATEST_SAMPLE:",
        [
            {
                "source_comment_id": comment.source_comment_id,
                "score": comment.score,
                "dimension": comment.dimension,
                "content": (comment.content or "")[:80],
            }
            for comment in latest_comments
        ],
    )


def main() -> None:
    db = SessionLocal()
    try:
        product_id = _prepare_product(db)
        status = CrawlerService.crawl_product(
            db=db,
            product_id=product_id,
            max_scroll_rounds=MAX_SCROLL_ROUNDS,
        )
        _print_summary(db, product_id, status)
    finally:
        db.close()


if __name__ == "__main__":
    main()
