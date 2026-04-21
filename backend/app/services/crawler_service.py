"""
爬虫服务
处理爬虫任务的业务逻辑
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.crawlers import JDCrawler
from app.models import Comment, Product
from app.models.product import ProductStatus
from app.schemas.product import ProductStatusResponse
from app.services.vector_store_service import VectorStoreService
from app.utils.logger import logger


class CrawlerService:
    """爬虫服务"""

    @staticmethod
    def _get_supported_crawler(platform: str):
        if platform == "jd":
            # 主程序联调阶段先使用可视浏览器，避免无头模式下页面重渲染导致评论入口失效。
            return JDCrawler(headless=False)
        raise ValueError(f"暂不支持的平台: {platform}")

    @staticmethod
    def get_product_status(db: Session, product_id: int) -> ProductStatusResponse:
        """获取商品状态"""
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError(f"商品不存在: {product_id}")
        return ProductStatusResponse.model_validate(product)

    @staticmethod
    def crawl_product(db: Session, product_id: int, max_scroll_rounds: int = 5) -> ProductStatusResponse:
        """按商品 ID 爬取商品评论"""
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError(f"商品不存在: {product_id}")

        crawler = CrawlerService._get_supported_crawler(product.source)

        try:
            # 先标准化商品基础信息，确保后续抓取使用的是平台标准链接。
            product_info = crawler.fetch_product_info(product.product_url)
            product.product_url = product_info["product_url"]
            if product_info.get("product_name"):
                product.product_name = product_info["product_name"]

            # 抓取开始前先把商品状态切到 CRAWLING，便于任务进度和失败原因可观测。
            product.crawl_status = ProductStatus.CRAWLING
            product.last_crawl_error = None
            db.commit()
            logger.info("商品 {} 状态更新为 CRAWLING", product_id)

            # 实际分页抓评论的逻辑在具体 crawler/base_crawler.crawl() 中完成，
            # 这里负责按商品 URL 触发抓取并接收清洗后的评论结果。
            logger.info(
                "正在爬取商品: {} (max_scroll_rounds={})",
                product.product_url,
                max_scroll_rounds,
            )
            comments_data = crawler.crawl(product.product_url, max_pages=max_scroll_rounds)

            if not comments_data:
                # 没抓到新评论不算失败，直接刷新评论总数和最后抓取时间。
                product.crawl_status = ProductStatus.COMPLETED
                product.comment_count = db.query(Comment).filter(Comment.product_id == product_id).count()
                product.last_crawled_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(product)
                return ProductStatusResponse.model_validate(product)

            saved_count = 0
            for comment_data in comments_data:
                # 以 source_comment_id 去重，避免同一商品重复抓取时反复写入相同评论。
                existing = db.query(Comment).filter(
                    Comment.product_id == product_id,
                    Comment.source_comment_id == comment_data.get("source_comment_id"),
                ).first()
                if existing:
                    logger.debug("Comment already exists: {}", comment_data.get("source_comment_id"))
                    continue

                comment = Comment(
                    product_id=product_id,
                    content=comment_data.get("content", ""),
                    score=comment_data.get("score", 0),
                    dimension=comment_data.get("dimension"),
                    dimension_score=comment_data.get("dimension_score"),
                    comment_time=comment_data.get("comment_time"),
                    source_comment_id=comment_data.get("source_comment_id"),
                    is_vectorized=False,
                )
                db.add(comment)
                saved_count += 1

            db.commit()

            # 评论落库后立即补写向量索引，保证后续 RAG 检索可以直接复用最新评论。
            vectorized_count = VectorStoreService.upsert_product_comments(db, product_id)

            # 抓取成功后统一回写商品状态、评论总量和最近抓取时间。
            product.crawl_status = ProductStatus.COMPLETED
            product.comment_count = db.query(Comment).filter(Comment.product_id == product_id).count()
            product.last_crawled_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(product)

            logger.info(
                "Product {} crawling completed: {} new comments saved, total {}",
                product_id,
                saved_count,
                product.comment_count,
            )
            logger.info(
                "Product comments vectorized after crawling: product_id={} vectorized_count={}",
                product_id,
                vectorized_count,
            )
            return ProductStatusResponse.model_validate(product)

        except Exception as e:
            logger.error(f"Crawl product error: {str(e)}")
            # 服务层只要任一步失败，就把商品状态标记为 FAILED，并保留最近错误信息。
            product.crawl_status = ProductStatus.FAILED
            product.last_crawl_error = str(e)
            db.commit()
            raise
        finally:
            crawler.close()

    @staticmethod
    def get_product_comments(db: Session, product_id: int, limit: int = 100) -> list:
        """获取商品的评论列表"""
        try:
            comments = db.query(Comment).filter(
                Comment.product_id == product_id
            ).order_by(Comment.created_at.desc()).limit(limit).all()
            return comments
        except Exception as e:
            logger.error(f"Get product comments error: {str(e)}")
            raise

    @staticmethod
    def get_comment_statistics(db: Session, product_id: int) -> dict:
        """获取商品评论统计"""
        try:
            from sqlalchemy import func

            total_count = db.query(func.count(Comment.id)).filter(
                Comment.product_id == product_id
            ).scalar()

            avg_score = db.query(func.avg(Comment.score)).filter(
                Comment.product_id == product_id
            ).scalar()

            score_distribution = {}
            for score in range(1, 6):
                count = db.query(func.count(Comment.id)).filter(
                    Comment.product_id == product_id,
                    Comment.score == score
                ).scalar()
                score_distribution[score] = count

            dimension_stats = {}
            dimensions = db.query(Comment.dimension).filter(
                Comment.product_id == product_id,
                Comment.dimension.isnot(None)
            ).distinct().all()

            for (dimension,) in dimensions:
                avg_dim_score = db.query(func.avg(Comment.dimension_score)).filter(
                    Comment.product_id == product_id,
                    Comment.dimension == dimension
                ).scalar()
                dimension_stats[dimension] = round(avg_dim_score, 2) if avg_dim_score else 0

            return {
                "total_count": total_count,
                "avg_score": round(avg_score, 2) if avg_score else 0,
                "score_distribution": score_distribution,
                "dimension_stats": dimension_stats
            }

        except Exception as e:
            logger.error(f"Get comment statistics error: {str(e)}")
            raise
