from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import func

from app.agents.llm import LLMUnavailableError
from app.agents.state import AnalysisWorkflowRuntime
from app.agents.rag_agent import RAGAgent
from app.agents.workflow import AnalysisWorkflow
from app.config import DEEPSEEK_API_KEY
from app.db.database import SessionLocal
from app.models import Comment, Product
from app.schemas.agent_protocol import RAGAgentResult, RAGEvidenceItem, RAGQueryPlan, ResponseStyle, RouteDecision, SQLAgentResult


class _FakeQuery:
    """模拟 SQLAlchemy query，满足 rag_agent 的最小查询需求。"""

    def __init__(self, comments):
        self._comments = comments

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._comments


class _FakeSession:
    """只为 rag_agent 提供评论查询能力的轻量 session。"""

    def __init__(self, comments):
        self._comments = comments

    def query(self, _model):
        return _FakeQuery(self._comments)


def _build_comment(*, content: str, score: int, dimension: str | None):
    return SimpleNamespace(
        content=content,
        score=score,
        dimension=dimension,
        created_at=datetime(2026, 4, 1, 12, 0, 0),
    )


def _build_route_decision() -> RouteDecision:
    return RouteDecision(
        need_sql=True,
        need_rag=True,
        need_visual=False,
        analysis_targets=["bad_review_distribution"],
        response_style=ResponseStyle.PROFESSIONAL_ANALYSIS,
        reason="用户希望了解差评集中原因，需要评论证据支撑。",
    )


def _get_real_product_with_comments(db):
    return (
        db.query(
            Product.id.label("product_id"),
            Product.source.label("source"),
            Product.external_product_id.label("external_product_id"),
            Product.product_name.label("product_name"),
            func.count(Comment.id).label("comment_count"),
        )
        .join(Comment, Comment.product_id == Product.id)
        .group_by(Product.id, Product.source, Product.external_product_id, Product.product_name)
        .order_by(func.count(Comment.id).desc(), Product.id.asc())
        .first()
    )


def test_rag_agent_run_passes_extended_context_to_planner_and_summarizer(monkeypatch):
    db = _FakeSession(
        [
            _build_comment(content="物流太慢了。", score=1, dimension="物流"),
            _build_comment(content="包装一般。", score=2, dimension="质量"),
        ]
    )

    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        assert temperature == 0.2
        if schema is RAGQueryPlan:
            assert payload["question"] == "请分析商品差评原因"
            assert payload["analysis_targets"] == ["bad_review_distribution"]
            assert payload["route_reason"] == "用户希望了解差评集中原因，需要评论证据支撑。"
            assert payload["response_style"] == ResponseStyle.PROFESSIONAL_ANALYSIS.value
            assert payload["sql_result_description"] == "差评主要集中在物流。"
            return RAGQueryPlan(queries=["商品差评原因", "物流吐槽"])
        if schema is RAGAgentResult:
            assert payload["queries"] == ["商品差评原因", "物流吐槽"]
            assert payload["route_reason"] == "用户希望了解差评集中原因，需要评论证据支撑。"
            assert payload["response_style"] == ResponseStyle.PROFESSIONAL_ANALYSIS.value
            assert payload["sql_result_description"] == "差评主要集中在物流。"
            assert len(payload["candidate_evidence"]) == 2
            return RAGAgentResult(
                queries=payload["queries"],
                evidence=[],
                insight="评论语义显示物流时效问题最突出。",
                insight_points=["物流相关吐槽最集中。", "典型问题是配送时效慢。"],
            )
        raise AssertionError(f"Unexpected schema: {schema}")

    monkeypatch.setattr("app.agents.rag_agent.invoke_structured_output", fake_invoke_structured_output)
    monkeypatch.setattr("app.agents.rag_agent.VectorStoreService.ensure_product_vectorized", lambda db, product_id: 0)
    monkeypatch.setattr(
        "app.agents.rag_agent.VectorStoreService.query_product_comments",
        lambda **_kwargs: [
            {"content": "物流太慢了。", "score": 1, "dimension": "物流", "similarity": 0.91},
            {"content": "包装一般。", "score": 2, "dimension": "质量", "similarity": 0.83},
        ],
    )

    result = RAGAgent.run(
        db=db,
        product_id=88,
        question="请分析商品差评原因",
        analysis_targets=["bad_review_distribution"],
        route_reason="用户希望了解差评集中原因，需要评论证据支撑。",
        response_style=ResponseStyle.PROFESSIONAL_ANALYSIS.value,
        sql_result_description="差评主要集中在物流。",
    )

    assert result.queries == ["商品差评原因", "物流吐槽"]
    assert len(result.evidence) == 2
    assert result.insight == "评论语义显示物流时效问题最突出。"
    assert result.insight_points == ["物流相关吐槽最集中。", "典型问题是配送时效慢。"]


def test_rag_agent_fallback_builds_insight_points_when_llm_unavailable(monkeypatch):
    db = _FakeSession([_build_comment(content="物流太慢了。", score=1, dimension="物流")])

    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        if schema is RAGQueryPlan:
            return RAGQueryPlan(queries=["物流差评"])
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.rag_agent.invoke_structured_output", fake_invoke_structured_output)
    monkeypatch.setattr("app.agents.rag_agent.VectorStoreService.ensure_product_vectorized", lambda db, product_id: 0)
    monkeypatch.setattr(
        "app.agents.rag_agent.VectorStoreService.query_product_comments",
        lambda **_kwargs: [{"content": "物流太慢了。", "score": 1, "dimension": "物流", "similarity": 0.91}],
    )

    result = RAGAgent.run(
        db=db,
        product_id=88,
        question="请分析物流差评原因",
        analysis_targets=["bad_review_distribution"],
    )

    assert result.insight
    assert result.insight_points == [result.insight]


def test_workflow_rag_agent_passes_route_reason_response_style_and_sql_description(monkeypatch):
    captured_kwargs = {}

    def fake_run(**kwargs):
        captured_kwargs.update(kwargs)
        return RAGAgentResult(
            queries=["物流吐槽"],
            evidence=[],
            insight="评论语义显示物流问题突出。",
            insight_points=["物流问题突出。"],
        )

    monkeypatch.setattr("app.agents.workflow.RAGAgent.run", fake_run)

    route_decision = _build_route_decision()
    sql_result = SQLAgentResult(tool_calls=[], metrics={}, description="差评主要集中在物流。")
    runtime = AnalysisWorkflowRuntime(
        db=object(),
        task=SimpleNamespace(question="请分析差评原因", product_id=88, product=None),
        set_task_state_fn=lambda *_args, **_kwargs: None,
        should_crawl_fn=lambda _product: False,
        crawl_product_fn=lambda *_args, **_kwargs: None,
        product_resolved_from="bound_product",
    )
    token = AnalysisWorkflow._runtime_context.set(runtime)
    try:
        result = AnalysisWorkflow._rag_agent(
            {
                "user_message": "请分析差评原因",
                "product_context": SimpleNamespace(product_id=88),
                "route_decision": route_decision,
                "sql_result": sql_result,
            }
        )
    finally:
        AnalysisWorkflow._runtime_context.reset(token)

    assert captured_kwargs["question"] == "请分析差评原因"
    assert captured_kwargs["route_reason"] == route_decision.reason
    assert captured_kwargs["response_style"] == route_decision.response_style.value
    assert captured_kwargs["sql_result_description"] == "差评主要集中在物流。"
    assert result["rag_result"].insight_points == ["物流问题突出。"]


def test_rag_agent_reranks_evidence_toward_negative_intent():
    evidence = [
        RAGEvidenceItem(content="物流很快，配送体验很好。", dimension="物流", score=5, similarity=0.92),
        RAGEvidenceItem(content="发货太慢了，下单三天后才出库。", dimension="物流", score=1, similarity=0.81),
        RAGEvidenceItem(content="做工不错，基本满意。", dimension="质量", score=5, similarity=0.84),
    ]

    reranked = RAGAgent._rerank_evidence_by_intent(
        evidence=evidence,
        question="请分析这个商品差评主要集中在哪些问题上",
        analysis_targets=["bad_review_distribution"],
        route_reason="用户需要评论证据解释差评原因。",
        sql_result_description="差评主要集中在物流维度。",
        queries=["差评", "物流问题"],
        limit=3,
    )

    assert reranked[0].content == "发货太慢了，下单三天后才出库。"


def test_rag_agent_reranks_evidence_toward_dimension_focus_without_forcing_negative():
    evidence = [
        RAGEvidenceItem(content="物流很快，配送体验很好。", dimension="物流", score=5, similarity=0.8),
        RAGEvidenceItem(content="做工扎实，质感不错。", dimension="质量", score=5, similarity=0.83),
        RAGEvidenceItem(content="包装一般，没有惊喜。", dimension="综合", score=3, similarity=0.82),
    ]

    reranked = RAGAgent._rerank_evidence_by_intent(
        evidence=evidence,
        question="请结合评论分析物流体验怎么样",
        analysis_targets=["dimension_stats"],
        route_reason="用户想了解物流体验，不限正负。",
        sql_result_description="物流维度需要重点解释。",
        queries=["物流体验", "发货配送"],
        limit=3,
    )

    assert reranked[0].dimension == "物流"


@pytest.mark.skipif(not DEEPSEEK_API_KEY, reason="DEEPSEEK_API_KEY 未配置，跳过真实大模型测试")
def test_rag_agent_with_real_llm():
    db = SessionLocal()
    try:
        try:
            real_product = _get_real_product_with_comments(db)
        except Exception as exc:
            pytest.skip(f"真实数据库不可用，跳过测试: {exc}")

        if real_product is None:
            pytest.skip("真实数据库中没有带评论数据的商品，跳过测试")

        result = RAGAgent.run(
            db=db,
            product_id=real_product.product_id,
            question="请结合评论证据分析这个商品差评主要集中在哪些问题上",
            analysis_targets=["bad_review_distribution", "dimension_stats"],
            route_reason="用户需要基于评论证据解释差评集中原因。",
            response_style=ResponseStyle.PROFESSIONAL_ANALYSIS.value,
            sql_result_description="统计结果显示差评主要集中在物流和质量维度。",
        )
        print("real_llm_rag_agent_result:", flush=True)
        print(
            {
                "product_id": real_product.product_id,
                "source": real_product.source,
                "external_product_id": real_product.external_product_id,
                "product_name": real_product.product_name,
                "comment_count": int(real_product.comment_count or 0),
            },
            flush=True,
        )
        print(result.model_dump_json(indent=2, exclude_none=True), flush=True)
    finally:
        db.close()

    assert isinstance(result.queries, list)
    assert len(result.queries) >= 1
    assert isinstance(result.evidence, list)
    assert isinstance(result.insight, str)
    assert result.insight.strip()
    assert isinstance(result.insight_points, list)
