"""
爬虫服务
处理爬虫任务的业务逻辑
"""

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.crawlers import JDCrawlerSimple
from app.models import Comment, Product
from app.models.product import ProductStatus
from app.schemas.product import ProductStatusResponse
from app.utils.link_extractor import LinkExtractor


class CrawlerService:
    """爬虫服务"""

    @staticmethod
    def _get_supported_crawler(platform: str):
        if platform == "jd":
            return JDCrawlerSimple()
        raise ValueError(f"暂不支持的平台: {platform}")

    @staticmethod
    def get_product_status(db: Session, product_id: int) -> ProductStatusResponse:
        """获取商品状态"""
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError(f"商品不存在: {product_id}")
        return ProductStatusResponse.model_validate(product)

    @staticmethod
    def resolve_product_by_url(db: Session, product_url: str) -> Product:
        """根据商品链接获取或创建商品记录"""
        link_info = LinkExtractor.extract_from_text(product_url)
        if not link_info:
            raise ValueError("商品链接格式不支持或无法识别商品 ID")

        crawler = CrawlerService._get_supported_crawler(link_info["platform"])
        product_info = crawler.fetch_product_info(link_info["url"])

        product = db.query(Product).filter(
            Product.source == product_info["source"],
            Product.external_product_id == product_info["external_product_id"],
        ).first()

        if product is None:
            product = Product(
                source=product_info["source"],
                external_product_id=product_info["external_product_id"],
                product_url=product_info["product_url"],
                product_name=product_info.get("product_name"),
                crawl_status=ProductStatus.PENDING,
            )
            db.add(product)
            db.commit()
            db.refresh(product)
            logger.info(
                "Created product for crawler: id={} source={} external_product_id={}",
                product.id,
                product.source,
                product.external_product_id,
            )
            return product

        product.product_url = product_info["product_url"]
        if product_info.get("product_name") and not product.product_name:
            product.product_name = product_info["product_name"]
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def crawl_product(db: Session, product_id: int, max_pages: int = 5) -> ProductStatusResponse:
        """按商品 ID 爬取商品评论"""
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError(f"商品不存在: {product_id}")

        crawler = CrawlerService._get_supported_crawler(product.source)

        try:
            product_info = crawler.fetch_product_info(product.product_url)
            product.product_url = product_info["product_url"]
            if product_info.get("product_name"):
                product.product_name = product_info["product_name"]

            product.crawl_status = ProductStatus.CRAWLING
            product.last_crawl_error = None
            db.commit()
            logger.info("Product {} status updated to CRAWLING", product_id)

            logger.info("Starting to crawl product: {}", product.product_url)
            comments_data = crawler.crawl(product.product_url, max_pages=max_pages)

            if not comments_data:
                product.crawl_status = ProductStatus.COMPLETED
                product.comment_count = db.query(Comment).filter(Comment.product_id == product_id).count()
                product.last_crawled_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(product)
                return ProductStatusResponse.model_validate(product)

            saved_count = 0
            for comment_data in comments_data:
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
            return ProductStatusResponse.model_validate(product)

        except Exception as e:
            logger.error(f"Crawl product error: {str(e)}")
            product.crawl_status = ProductStatus.FAILED
            product.last_crawl_error = str(e)
            db.commit()
            raise

    @staticmethod
    def crawl_product_by_url(db: Session, product_url: str, max_pages: int = 5) -> ProductStatusResponse:
        """按商品链接解析、建档并执行爬取"""
        product = CrawlerService.resolve_product_by_url(db, product_url)
        return CrawlerService.crawl_product(db, product.id, max_pages=max_pages)

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
