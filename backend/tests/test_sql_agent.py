from __future__ import annotations

from app.agents.sql_agent import SQLAgent
from app.main import app
from app.models import Comment, Product
from app.models.product import ProductStatus


def test_sql_agent_aggregates_comment_statistics(client) -> None:
    """SQL Agent 应输出更结构化的评论统计结果。"""
    db = app.state.testing_sessionmaker()
    try:
        product = Product(
            source="jd",
            external_product_id="sql-1001",
            product_url="https://item.jd.com/sql-1001.html",
            product_name="SQL Agent 测试商品",
            crawl_status=ProductStatus.COMPLETED,
        )
        db.add(product)
        db.flush()

        db.add_all(
            [
                Comment(
                    product_id=product.id,
                    content="物流很慢，包装一般。",
                    score=2,
                    dimension="物流",
                    dimension_score=2,
                    source_comment_id="sql-comment-1",
                ),
                Comment(
                    product_id=product.id,
                    content="物流还可以，但是客服响应慢。",
                    score=3,
                    dimension="物流",
                    dimension_score=3,
                    source_comment_id="sql-comment-2",
                ),
                Comment(
                    product_id=product.id,
                    content="质量不错，做工挺扎实。",
                    score=5,
                    dimension="质量",
                    dimension_score=5,
                    source_comment_id="sql-comment-3",
                ),
            ]
        )
        db.commit()

        route_plan = {
            "focus_dimensions": ["物流", "质量"],
        }
        stats = SQLAgent.aggregate_comments(db, product.id, route_plan)

        assert stats["total_count"] == 3
        assert stats["avg_score"] == 3.33
        assert stats["low_score_count"] == 1
        assert stats["bad_rate"] == 0.3333
        assert stats["score_distribution"][2] == 1
        assert stats["score_distribution"][3] == 1
        assert stats["score_distribution"][5] == 1
        assert stats["dimension_stats"]["物流"]["comment_count"] == 2
        assert stats["dimension_stats"]["质量"]["avg_score"] == 5.0
        assert "物流" in stats["focus_dimension_stats"]
        assert "质量" in stats["focus_dimension_stats"]
    finally:
        db.close()
