from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import duckdb
import pytest
from sqlalchemy import func

from app.agents.llm import LLMUnavailableError
from app.agents.sql_agent import SQLAgent
from app.agents.sql_tools import SQLMetricsTools
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


def _build_comment(
    *,
    score: int,
    dimension: str | None,
    dimension_score: int | None = None,
    content: str = "",
    comment_time: datetime | None = None,
):
    return SimpleNamespace(
        score=score,
        dimension=dimension,
        dimension_score=dimension_score,
        content=content,
        comment_time=comment_time,
    )


def _build_comments_df():
    comments = [
        _build_comment(
            score=5,
            dimension="质量",
            content="这款固态硬盘速度非常快而且安装方便，日常使用很稳定，连续读写表现也很顺畅，作为系统盘和游戏盘都很合适。",
            comment_time=datetime(2026, 1, 5, 10, 0, 0),
        ),
        _build_comment(
            score=4,
            dimension="质量",
            content="速度不错，拷贝大文件时表现稳定，散热也还可以。",
            comment_time=datetime(2026, 1, 18, 12, 0, 0),
        ),
        _build_comment(
            score=2,
            dimension="质量",
            content="重载写入时温度偏高，需要额外散热片。",
            comment_time=datetime(2026, 2, 3, 9, 0, 0),
        ),
        _build_comment(
            score=1,
            dimension="物流",
            content="物流速度慢，包装也有破损。",
            comment_time=datetime(2026, 2, 10, 20, 0, 0),
        ),
        _build_comment(
            score=3,
            dimension="物流",
            content="发货速度一般，中规中矩。",
            comment_time=datetime(2026, 2, 11, 20, 0, 0),
        ),
        _build_comment(
            score=5,
            dimension="售后",
            content="售后响应很快，换新流程很顺畅，整体服务很好。",
            comment_time=datetime(2026, 3, 2, 8, 0, 0),
        ),
    ]
    return SQLMetricsTools.load_comments_df(_FakeSession(comments), product_id=1)


def _with_conn(assertions):
    comments_df = _build_comments_df()
    conn = duckdb.connect(":memory:")
    try:
        conn.register("comments_df", comments_df)
        assertions(conn)
    finally:
        conn.close()


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
            assert payload["question"] == "商品差评率是多少"
            return SQLToolPlan(
                tool_calls=[
                    SQLToolCall(tool="get_bad_review_rate", args={"product_id": -1}),
                    SQLToolCall(tool="get_bad_review_rate", args={"product_id": 999}),
                    SQLToolCall(tool="get_score_summary", args={"product_id": 88}),
                ]
            )
        if schema is SQLAgentResult:
            raise LLMUnavailableError("force empty result")
        raise AssertionError(f"Unexpected schema: {schema}")

    monkeypatch.setattr("app.agents.sql_agent.invoke_structured_output", fake_invoke_structured_output)

    result = SQLAgent.run(
        db=db,
        product_id=88,
        question="商品差评率是多少",
    )
    print("sanitized_sql_agent_result:", result.model_dump_json(indent=2))

    captured = capsys.readouterr()
    assert "sanitized_sql_agent_result:" in captured.out
    assert result.tool_calls == []
    assert result.metrics == {}
    assert result.description == ""


def test_sql_agent_returns_empty_when_tool_planner_unavailable(monkeypatch, capsys):
    db = _FakeSession([_build_comment(score=5, dimension="质量")])

    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        assert isinstance(temperature, float)
        if schema is SQLToolPlan:
            raise LLMUnavailableError("force empty plan")
        raise AssertionError("summarizer should not be invoked when planner returns empty")

    monkeypatch.setattr("app.agents.sql_agent.invoke_structured_output", fake_invoke_structured_output)

    result = SQLAgent.run(
        db=db,
        product_id=88,
        question="先别统计",
    )
    print("empty_plan_sql_agent_result:", result.model_dump_json(indent=2))

    captured = capsys.readouterr()
    assert "empty_plan_sql_agent_result:" in captured.out
    assert result.tool_calls == []
    assert result.metrics == {}
    assert result.description == ""


def test_sql_agent_score_summary_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_score_summary(conn)
        assert result == {
            "score_summary": {
                "total_count": 6,
                "avg_score": 3.33,
                "low_score_count": 2,
            }
        }

    _with_conn(assertions)


def test_sql_agent_score_distribution_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_score_distribution(conn)
        assert result == {
            "score_distribution": {
                1: 1,
                2: 1,
                3: 1,
                4: 1,
                5: 2,
            }
        }

    _with_conn(assertions)


def test_sql_agent_bad_review_rate_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_bad_review_rate(conn)
        assert result == {"bad_review_rate": 0.3333}

    _with_conn(assertions)


def test_sql_agent_positive_review_rate_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_positive_review_rate(conn)
        assert result == {
            "positive_review_rate": {
                "total_count": 6,
                "positive_count": 3,
                "positive_rate": 0.5,
            }
        }

    _with_conn(assertions)


def test_sql_agent_score_band_distribution_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_score_band_distribution(conn)
        assert result == {
            "score_band_distribution": {
                "positive": 3,
                "neutral": 1,
                "negative": 2,
            }
        }

    _with_conn(assertions)


def test_sql_agent_dimension_stats_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_dimension_stats(conn)
        assert result == {
            "dimension_stats": {
                "质量": {
                    "comment_count": 3,
                    "avg_score": 3.67,
                    "bad_review_rate": 0.3333,
                    "bad_review_count": 1,
                },
                "物流": {
                    "comment_count": 2,
                    "avg_score": 2.0,
                    "bad_review_rate": 0.5,
                    "bad_review_count": 1,
                },
                "售后": {
                    "comment_count": 1,
                    "avg_score": 5.0,
                    "bad_review_rate": 0.0,
                    "bad_review_count": 0,
                },
            }
        }

    _with_conn(assertions)


def test_sql_agent_bad_review_distribution_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_bad_review_distribution(conn)
        assert result == {
            "bad_review_distribution": {
                "质量": 1,
                "物流": 1,
            }
        }

    _with_conn(assertions)


def test_sql_agent_dimension_rankings_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_dimension_rankings(conn)
        assert result == {
            "dimension_rankings": {
                "by_comment_count": [
                    {"dimension": "质量", "comment_count": 3},
                    {"dimension": "物流", "comment_count": 2},
                    {"dimension": "售后", "comment_count": 1},
                ],
                "by_avg_score": [
                    {"dimension": "售后", "avg_score": 5.0},
                    {"dimension": "质量", "avg_score": 3.67},
                    {"dimension": "物流", "avg_score": 2.0},
                ],
                "by_bad_review_rate": [
                    {"dimension": "物流", "bad_review_rate": 0.5},
                    {"dimension": "质量", "bad_review_rate": 0.3333},
                    {"dimension": "售后", "bad_review_rate": 0.0},
                ],
            }
        }

    _with_conn(assertions)


def test_sql_agent_monthly_score_trend_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_monthly_score_trend(conn)
        assert result == {
            "monthly_score_trend": [
                {
                    "month": "2026-01",
                    "comment_count": 2,
                    "avg_score": 4.5,
                    "bad_review_rate": 0.0,
                    "bad_review_count": 0,
                },
                {
                    "month": "2026-02",
                    "comment_count": 3,
                    "avg_score": 2.0,
                    "bad_review_rate": 0.6667,
                    "bad_review_count": 2,
                },
                {
                    "month": "2026-03",
                    "comment_count": 1,
                    "avg_score": 5.0,
                    "bad_review_rate": 0.0,
                    "bad_review_count": 0,
                },
            ]
        }

    _with_conn(assertions)


def test_sql_agent_dimension_score_distribution_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_dimension_score_distribution(conn)
        assert result == {
            "dimension_score_distribution": {
                "售后": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 1},
                "物流": {"1": 1, "2": 0, "3": 1, "4": 0, "5": 0},
                "质量": {"1": 0, "2": 1, "3": 0, "4": 1, "5": 1},
            }
        }

    _with_conn(assertions)


def test_sql_agent_dimension_coverage_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_dimension_coverage(conn)
        assert result == {
            "dimension_coverage": {
                "质量": 3,
                "物流": 2,
                "售后": 1,
            }
        }

    _with_conn(assertions)


def test_sql_agent_comment_length_stats_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_comment_length_stats(conn)
        assert result["comment_length_stats"]["total_count"] == 6
        assert result["comment_length_stats"]["long_comment_count"] >= 1
        assert result["comment_length_stats"]["avg_length"] > 0
        assert result["comment_length_stats"]["median_length"] > 0

    _with_conn(assertions)


def test_sql_agent_low_score_dimension_pairs_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_low_score_dimension_pairs(conn)
        assert result == {
            "low_score_dimension_pairs": [
                {"dimension": "物流", "bad_count": 1},
                {"dimension": "质量", "bad_count": 1},
            ]
        }

    _with_conn(assertions)


def test_sql_agent_dimension_polarization_tool_returns_expected_metrics():
    def assertions(conn):
        result = SQLMetricsTools.get_dimension_polarization(conn)
        assert result == {
            "dimension_polarization": {
                "售后": {
                    "avg_score": 5.0,
                    "high_score_ratio": 1.0,
                    "low_score_ratio": 0.0,
                    "polarization_index": 1.0,
                },
                "物流": {
                    "avg_score": 2.0,
                    "high_score_ratio": 0.0,
                    "low_score_ratio": 0.5,
                    "polarization_index": 0.5,
                },
                "质量": {
                    "avg_score": 3.67,
                    "high_score_ratio": 0.6667,
                    "low_score_ratio": 0.3333,
                    "polarization_index": 1.0,
                },
            }
        }

    _with_conn(assertions)


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
