from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import func

from app.agents.state import AnalysisWorkflowRuntime
from app.agents.workflow import AnalysisWorkflow
from app.config import DEEPSEEK_API_KEY
from app.db.database import SessionLocal
from app.models import Comment, Product


def _get_real_product_with_comments(db):
    """选择一个真实库中评论数最多的商品，保证工作流有足够数据可分析。"""
    return (
        db.query(Product, func.count(Comment.id).label("comment_count"))
        .join(Comment, Comment.product_id == Product.id)
        .group_by(Product.id)
        .order_by(func.count(Comment.id).desc(), Product.id.asc())
        .first()
    )


@pytest.mark.skipif(not DEEPSEEK_API_KEY, reason="DEEPSEEK_API_KEY 未配置，跳过真实工作流测试")
def test_analysis_workflow_with_real_llm_and_db():
    """真实调用 workflow 主链路，并打印关键中间结果方便观察整链路表现。"""
    db = SessionLocal()
    try:
        try:
            real_product_row = _get_real_product_with_comments(db)
        except Exception as exc:
            pytest.skip(f"真实数据库不可用，跳过测试: {exc}")

        if real_product_row is None:
            pytest.skip("真实数据库中没有带评论数据的商品，跳过测试")

        product, comment_count = real_product_row
        question = "请结合评论证据分析这个商品差评主要集中在哪些问题上，并给出统计结论。"
        task = SimpleNamespace(
            question=question,
            product_id=product.id,
            product=product,
        )
        runtime = AnalysisWorkflowRuntime(
            db=db,
            task=task,
            set_task_state_fn=lambda *_args, **_kwargs: None,
            should_crawl_fn=lambda _product: False,
            crawl_product_fn=lambda *_args, **_kwargs: None,
            product_resolved_from="bound_product",
        )

        workflow_state = AnalysisWorkflow.run(
            {
                "user_message": question,
                "retry_count": 0,
                "max_retry": 1,
            },
            runtime=runtime,
        )
        print("real_workflow_context:", flush=True)
        print(
            {
                "product_id": product.id,
                "source": product.source,
                "external_product_id": product.external_product_id,
                "product_name": product.product_name,
                "comment_count": int(comment_count or 0),
                "question": question,
            },
            flush=True,
        )
        for key in (
            "route_decision",
            "sql_result",
            "rag_result",
            "answer_draft",
            "master_decision",
        ):
            value = workflow_state.get(key)
            if value is None:
                continue
            print(f"workflow_{key}:", flush=True)
            print(value.model_dump_json(indent=2, exclude_none=True), flush=True)
    finally:
        db.close()

    route_decision = workflow_state.get("route_decision")
    sql_result = workflow_state.get("sql_result")
    rag_result = workflow_state.get("rag_result")
    answer_draft = workflow_state.get("answer_draft")
    master_decision = workflow_state.get("master_decision")

    assert route_decision is not None
    assert route_decision.need_sql is True
    assert route_decision.need_rag is True
    assert sql_result is not None
    assert isinstance(sql_result.metrics, dict)
    assert rag_result is not None
    assert len(rag_result.queries) >= 1
    assert answer_draft is not None
    assert answer_draft.answer.strip()
    assert master_decision is not None
    assert master_decision.reason.strip()
