from __future__ import annotations

from app.agents.rag_agent import RAGAgent
from app.main import app
from app.models import Comment, Product
from app.models.product import ProductStatus


def test_rag_agent_prioritizes_focus_dimension_comments(client) -> None:
    """RAG Agent 应优先返回与重点维度更相关的评论。"""
    db = app.state.testing_sessionmaker()
    try:
        product = Product(
            source="jd",
            external_product_id="rag-1001",
            product_url="https://item.jd.com/rag-1001.html",
            product_name="RAG Agent 测试商品",
            crawl_status=ProductStatus.COMPLETED,
        )
        db.add(product)
        db.flush()

        db.add_all(
            [
                Comment(
                    product_id=product.id,
                    content="物流太慢了，配送延迟两天，体验很差。",
                    score=1,
                    dimension="物流",
                    dimension_score=1,
                    source_comment_id="rag-comment-1",
                ),
                Comment(
                    product_id=product.id,
                    content="音质不错，续航也可以。",
                    score=5,
                    dimension="性能",
                    dimension_score=5,
                    source_comment_id="rag-comment-2",
                ),
                Comment(
                    product_id=product.id,
                    content="客服回复慢，售后处理一般。",
                    score=2,
                    dimension="售后",
                    dimension_score=2,
                    source_comment_id="rag-comment-3",
                ),
            ]
        )
        db.commit()

        route_plan = {
            "focus_dimensions": ["物流", "售后"],
            "rag_queries": ["物流 相关用户评价", "售后 相关用户评价"],
        }
        evidence = RAGAgent.retrieve_evidence(
            db=db,
            product_id=product.id,
            question="请分析这款商品的差评，重点看物流和售后问题。",
            route_plan=route_plan,
            limit=2,
        )

        assert len(evidence) == 2
        assert evidence[0]["dimension"] in {"物流", "售后"}
        assert evidence[0]["similarity"] >= evidence[1]["similarity"]
        assert all(item["dimension"] != "性能" for item in evidence)
    finally:
        db.close()
