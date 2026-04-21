"""Seed a small demo product with analysis-friendly comments."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models import Comment, Product
from app.models.product import ProductStatus
from app.services.vector_store_service import VectorStoreService
from app.utils.logger import logger


DEMO_PRODUCT = {
    "source": "jd",
    "external_product_id": "1000001",
    "product_url": "https://item.jd.com/1000001.html",
    "product_name": "MA-ESAS 分析演示商品",
}

DEMO_COMMENTS = [
    {"source_comment_id": "demo-analysis-001", "dimension": "物流", "score": 1, "content": "发货太慢了，下单三天后才出库，物流体验很差。"},
    {"source_comment_id": "demo-analysis-002", "dimension": "物流", "score": 2, "content": "配送延迟严重，快递包装还有破损。"},
    {"source_comment_id": "demo-analysis-003", "dimension": "物流", "score": 2, "content": "到货时间比预期晚很多，催单也没有明显改善。"},
    {"source_comment_id": "demo-analysis-004", "dimension": "售后", "score": 2, "content": "售后回复很慢，退款流程拖了好几天。"},
    {"source_comment_id": "demo-analysis-005", "dimension": "售后", "score": 3, "content": "客服态度还行，但问题解决效率偏低。"},
    {"source_comment_id": "demo-analysis-006", "dimension": "售后", "score": 2, "content": "申请换货后迟迟没有进展，沟通成本很高。"},
    {"source_comment_id": "demo-analysis-007", "dimension": "质量", "score": 4, "content": "整体做工还可以，日常使用没有明显问题。"},
    {"source_comment_id": "demo-analysis-008", "dimension": "质量", "score": 5, "content": "材质不错，拿在手里质感比预期好。"},
    {"source_comment_id": "demo-analysis-009", "dimension": "质量", "score": 4, "content": "使用一周后表现稳定，暂时没发现质量缺陷。"},
    {"source_comment_id": "demo-analysis-010", "dimension": "价格", "score": 3, "content": "价格中规中矩，没有特别惊喜，但还能接受。"},
    {"source_comment_id": "demo-analysis-011", "dimension": "价格", "score": 4, "content": "活动价入手还算划算，性价比可以。"},
    {"source_comment_id": "demo-analysis-012", "dimension": "性能", "score": 5, "content": "性能表现不错，运行流畅，体验比较稳定。"},
    {"source_comment_id": "demo-analysis-013", "dimension": "性能", "score": 4, "content": "响应速度挺快，日常场景基本够用。"},
    {"source_comment_id": "demo-analysis-014", "dimension": "综合", "score": 3, "content": "优点和缺点都比较明显，整体属于能用但不惊艳。"},
    {"source_comment_id": "demo-analysis-015", "dimension": "综合", "score": 2, "content": "如果更看重物流和售后，这款商品需要谨慎考虑。"},
]


def parse_args() -> argparse.Namespace:
    """解析脚本参数。"""
    parser = argparse.ArgumentParser(description="Seed demo analysis comments into MySQL.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing demo comments for the demo product before seeding.",
    )
    return parser.parse_args()


def get_or_create_demo_product(db: Session) -> Product:
    """获取演示商品，不存在时自动创建。"""
    product = db.query(Product).filter(
        Product.source == DEMO_PRODUCT["source"],
        Product.external_product_id == DEMO_PRODUCT["external_product_id"],
    ).first()
    if product is None:
        product = Product(
            source=DEMO_PRODUCT["source"],
            external_product_id=DEMO_PRODUCT["external_product_id"],
            product_url=DEMO_PRODUCT["product_url"],
            product_name=DEMO_PRODUCT["product_name"],
            crawl_status=ProductStatus.COMPLETED,
        )
        db.add(product)
        db.flush()
        logger.info(
            "Created demo product: product_id={} external_product_id={}",
            product.id,
            product.external_product_id,
        )
    else:
        product.product_url = DEMO_PRODUCT["product_url"]
        product.product_name = DEMO_PRODUCT["product_name"]
        product.crawl_status = ProductStatus.COMPLETED
        logger.info(
            "Reusing demo product: product_id={} external_product_id={}",
            product.id,
            product.external_product_id,
        )
    return product


def reset_demo_comments(db: Session, product: Product) -> int:
    """删除当前演示商品下的历史演示评论。"""
    VectorStoreService.delete_product_comments(product.id)
    deleted_count = (
        db.query(Comment)
        .filter(
            Comment.product_id == product.id,
            Comment.source_comment_id.like("demo-analysis-%"),
        )
        .delete(synchronize_session=False)
    )
    logger.info(
        "Reset demo comments: product_id={} deleted_count={}",
        product.id,
        deleted_count,
    )
    return int(deleted_count or 0)


def upsert_demo_comments(db: Session, product: Product) -> tuple[int, int]:
    """写入或更新演示评论，确保重复执行不会无限重复。"""
    created_count = 0
    updated_count = 0
    base_time = datetime.now(timezone.utc) - timedelta(days=2)

    for index, item in enumerate(DEMO_COMMENTS):
        comment = db.query(Comment).filter(
            Comment.product_id == product.id,
            Comment.source_comment_id == item["source_comment_id"],
        ).first()

        if comment is None:
            comment = Comment(
                product_id=product.id,
                source_comment_id=item["source_comment_id"],
                content=item["content"],
                score=item["score"],
                dimension=item["dimension"],
                dimension_score=item["score"],
                comment_time=base_time + timedelta(hours=index),
            )
            db.add(comment)
            created_count += 1
        else:
            comment.content = item["content"]
            comment.score = item["score"]
            comment.dimension = item["dimension"]
            comment.dimension_score = item["score"]
            comment.comment_time = base_time + timedelta(hours=index)
            updated_count += 1

    logger.info(
        "Upserted demo comments: product_id={} created_count={} updated_count={}",
        product.id,
        created_count,
        updated_count,
    )
    return created_count, updated_count


def refresh_product_snapshot(db: Session, product: Product) -> None:
    """刷新演示商品的评论统计和抓取时间。"""
    db.flush()
    product.comment_count = db.query(Comment).filter(Comment.product_id == product.id).count()
    product.last_crawled_at = datetime.now(timezone.utc)
    product.last_crawl_error = None
    product.crawl_status = ProductStatus.COMPLETED
    logger.info(
        "Refreshed demo product snapshot: product_id={} comment_count={}",
        product.id,
        product.comment_count,
    )


def seed_demo_analysis_data(reset: bool) -> None:
    """执行演示分析数据写入。"""
    db = SessionLocal()
    try:
        product = get_or_create_demo_product(db)
        deleted_count = 0
        if reset:
            deleted_count = reset_demo_comments(db, product)

        created_count, updated_count = upsert_demo_comments(db, product)
        refresh_product_snapshot(db, product)
        vectorized_count = VectorStoreService.upsert_product_comments(db, product.id)
        db.commit()
        db.refresh(product)

        print("Demo analysis data is ready.")
        print(f"Product URL: {product.product_url}")
        print(f"Product ID: {product.external_product_id}")
        print(f"Total comments: {product.comment_count}")
        print(f"Created comments: {created_count}")
        print(f"Updated comments: {updated_count}")
        print(f"Deleted comments: {deleted_count}")
        print(f"Vectorized comments: {vectorized_count}")
        print("Suggested prompt: 请分析这款商品的差评，重点看物流和售后问题。")
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to seed demo analysis data: {}", exc)
        raise
    finally:
        db.close()


def main() -> None:
    """脚本入口。"""
    args = parse_args()
    seed_demo_analysis_data(reset=args.reset)


if __name__ == "__main__":
    main()
