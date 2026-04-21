from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import func

from app.agents.llm import LLMUnavailableError
from app.agents.sql_agent import SQLAgent
from app.config import DEEPSEEK_API_KEY
from app.db.database import SessionLocal
from app.models import Comment, Product
from app.schemas.agent_protocol import SQLAgentResult, SQLToolCall, SQLToolPlan


class _FakeQuery:
    def __init__(self, comments):
        self._comments = comments

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._comments


class _FakeSession:
    def __init__(self, comments):
        self._comments = comments

    def query(self, _model):
        return _FakeQuery(self._comments)


def _build_comment(*, score: int, dimension: str | None, dimension_score: int | None = None):
    return SimpleNamespace(
        score=score,
        dimension=dimension,
        dimension_score=dimension_score,
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


def test_sql_agent_run_executes_only_sanitized_controlled_tools(monkeypatch, capsys):
    comments = [
        _build_comment(score=1, dimension="物流"),
        _build_comment(score=2, dimension="物流"),
        _build_comment(score=5, dimension="质量"),
    ]
    db = _FakeSession(comments)

    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        assert isinstance(temperature, float)
        if schema is SQLToolPlan:
            assert payload["product_id"] == 88
            assert payload["analysis_targets"] == ["bad_review_rate"]
            return SQLToolPlan(
                tool_calls=[
                    SQLToolCall(tool="get_bad_review_rate", args={"product_id": -1}),
                    SQLToolCall(tool="get_bad_review_rate", args={"product_id": 999}),
                    SQLToolCall(tool="get_score_summary", args={"product_id": 88}),
                ]
            )
        if schema is SQLAgentResult:
            raise LLMUnavailableError("force local summary")
        raise AssertionError(f"Unexpected schema: {schema}")

    monkeypatch.setattr("app.agents.sql_agent.invoke_structured_output", fake_invoke_structured_output)

    result = SQLAgent.run(
        db=db,
        product_id=88,
        question="商品差评率是多少",
        analysis_targets=["bad_review_rate"],
    )
    print("sanitized_sql_agent_result:", result.model_dump_json(indent=2))

    captured = capsys.readouterr()
    assert "sanitized_sql_agent_result:" in captured.out
    assert result.tool_calls == [SQLToolCall(tool="get_bad_review_rate", args={"product_id": 88})]
    assert result.metrics == {"bad_review_rate": 0.6667}
    assert "66.7%" in result.description
    assert "score_summary" not in result.metrics


def test_sql_agent_run_with_empty_analysis_targets_does_not_expand_scope(monkeypatch, capsys):
    db = _FakeSession([_build_comment(score=5, dimension="质量")])

    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        assert isinstance(temperature, float)
        if schema is SQLAgentResult:
            raise LLMUnavailableError("force local summary")
        raise AssertionError("tool planner should not be invoked when analysis_targets is empty")

    monkeypatch.setattr("app.agents.sql_agent.invoke_structured_output", fake_invoke_structured_output)

    result = SQLAgent.run(
        db=db,
        product_id=88,
        question="先别统计",
        analysis_targets=[],
    )
    print("empty_target_sql_agent_result:", result.model_dump_json(indent=2))

    captured = capsys.readouterr()
    assert "empty_target_sql_agent_result:" in captured.out
    assert result.tool_calls == []
    assert result.metrics == {}
    assert result.description == "当前未指定统计分析目标，sql_agent 未执行统计工具。"


@pytest.mark.skipif(not DEEPSEEK_API_KEY, reason="DEEPSEEK_API_KEY 未配置，跳过真实大模型测试")
def test_sql_agent_with_real_llm():
    db = SessionLocal()
    try:
        try:
            real_product = _get_real_product_with_comments(db)
        except Exception as exc:
            pytest.skip(f"真实数据库不可用，跳过测试: {exc}")

        if real_product is None:
            pytest.skip("真实数据库中没有带评论数据的商品，跳过测试")

        result = SQLAgent.run(
            db=db,
            product_id=real_product.product_id,
            question="请分析这个商品的差评率和差评分布，并简要总结统计发现",
            analysis_targets=["bad_review_rate", "bad_review_distribution"],
        )
        print("real_llm_sql_agent_result:", flush=True)
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
        print(result.model_dump_json(indent=2), flush=True)
    finally:
        db.close()

    assert isinstance(result.tool_calls, list)
    assert isinstance(result.metrics, dict)
    assert isinstance(result.description, str)
    assert "bad_review_rate" in result.metrics
    assert "bad_review_distribution" in result.metrics
