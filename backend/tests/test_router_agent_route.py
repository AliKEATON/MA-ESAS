from __future__ import annotations

import pytest

from app.agents.router_agent import RouterAgent
from app.config import DEEPSEEK_API_KEY
from app.schemas.agent_protocol import ResponseStyle, RouteDecision


def test_route_with_mocked_llm(monkeypatch, capsys):
    question = "分析商品差评分布并给出原因，顺便做可视化"

    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        assert isinstance(temperature, float)
        assert payload["question"] == question
        assert payload["has_product"] is True
        assert schema is RouteDecision
        return RouteDecision(
            need_sql=True,
            need_rag=True,
            need_visual=True,
            analysis_targets=["bad_review_rate", "bad_review_distribution"],
            response_style=ResponseStyle.PROFESSIONAL_ANALYSIS,
            reason="测试桩：需要统计、语义分析与可视化。",
        )

    monkeypatch.setattr("app.agents.router_agent.invoke_structured_output", fake_invoke_structured_output)

    result = RouterAgent.route(question=question, has_product=True)
    print("mock_llm_route_result:", result.model_dump_json(indent=2))

    captured = capsys.readouterr()
    assert "mock_llm_route_result:" in captured.out
    assert result.need_sql is True
    assert result.need_rag is True
    assert result.need_visual is True
    assert result.analysis_targets == ["bad_review_rate", "bad_review_distribution"]


def test_route_without_product_uses_fallback_result(capsys):
    result = RouterAgent.route(question="分析这个商品评分情况", has_product=False)
    print("no_product_route_result:", result.model_dump_json(indent=2))

    captured = capsys.readouterr()
    assert "no_product_route_result:" in captured.out
    assert result.need_sql is False
    assert result.need_rag is False
    assert result.need_visual is False
    assert result.analysis_targets == []
    assert result.response_style == ResponseStyle.BRIEF_ANSWER


@pytest.mark.skipif(not DEEPSEEK_API_KEY, reason="DEEPSEEK_API_KEY 未配置，跳过真实大模型测试")
def test_route_with_real_llm():
    result = RouterAgent.route(
        question="请分析这款商品的差评分布，并给出用户吐槽原因，同时做一个可视化建议",
        has_product=True,
    )
    print("real_llm_route_result:")
    print(result.model_dump_json(indent=2))

    assert isinstance(result.need_sql, bool)
    assert isinstance(result.need_rag, bool)
    assert isinstance(result.need_visual, bool)
    assert isinstance(result.analysis_targets, list)
    assert isinstance(result.reason, str)
