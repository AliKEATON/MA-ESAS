from __future__ import annotations

import pytest

from app.agents.llm import LLMUnavailableError
from app.agents.master_agent import MasterAgent
from app.agents.workflow import AnalysisWorkflow
from app.config import DEEPSEEK_API_KEY
from app.schemas.agent_protocol import (
    AnswerDraft,
    ChartSeries,
    ChartSpec,
    MasterDecision,
    MasterDecisionType,
    ResponseStyle,
    RouteDecision,
    SupportedChartType,
    VisualAgentResult,
)


def _build_route_decision(*, need_visual: bool = False) -> RouteDecision:
    return RouteDecision(
        need_sql=True,
        need_rag=False,
        need_visual=need_visual,
        response_style=ResponseStyle.PROFESSIONAL_ANALYSIS,
        reason="测试 master_agent 使用",
    )


def test_master_agent_run_passes_question_and_answer_points_to_llm(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        assert payload["question"] == "请总结当前分析结果是否完整"
        assert payload["answer_text"] == "这是候选回答"
        assert payload["answer_points"] == ["结论1", "结论2"]
        return MasterDecision(
            decision=MasterDecisionType.PASS,
            reason="通过",
            missing_items=[],
            retry_from=None,
        )

    monkeypatch.setattr("app.agents.master_agent.invoke_structured_output", fake_invoke_structured_output)

    result = MasterAgent.run(
        question="请总结当前分析结果是否完整",
        route_decision=_build_route_decision(),
        answer_text="这是候选回答",
        answer_points=["结论1", "结论2"],
    )

    assert result.decision == MasterDecisionType.PASS
    assert result.missing_items == []


def test_master_agent_fallback_marks_empty_answer_points_as_missing(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.master_agent.invoke_structured_output", fake_invoke_structured_output)

    result = MasterAgent.run(
        question="请总结当前分析结果是否完整",
        route_decision=_build_route_decision(),
        answer_text="这是候选回答",
        answer_points=[],
        retry_count=0,
        max_retry=1,
    )

    assert result.decision == MasterDecisionType.RETRY
    assert result.retry_from is not None
    assert result.retry_from.value == "answer_agent"
    assert "answer_points" in result.missing_items


def test_master_agent_fallback_marks_weak_answer_points_as_missing(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.master_agent.invoke_structured_output", fake_invoke_structured_output)

    result = MasterAgent.run(
        question="请总结当前分析结果是否完整",
        route_decision=_build_route_decision(),
        answer_text="这是候选回答",
        answer_points=["已分析", "图表"],
        retry_count=0,
        max_retry=1,
    )

    assert result.decision == MasterDecisionType.RETRY
    assert result.retry_from is not None
    assert result.retry_from.value == "answer_agent"
    assert "answer_points" in result.missing_items


def test_master_agent_fallback_marks_off_topic_answer_as_missing(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.master_agent.invoke_structured_output", fake_invoke_structured_output)

    result = MasterAgent.run(
        question="analyze logistics issues",
        route_decision=_build_route_decision(),
        answer_text="generic summary only",
        answer_points=["specific evidence point"],
        retry_count=0,
        max_retry=1,
    )

    assert result.decision == MasterDecisionType.RETRY
    assert result.retry_from is not None
    assert result.retry_from.value == "answer_agent"
    assert "answer" in result.missing_items


def test_workflow_master_agent_passes_question_and_answer_points(monkeypatch):
    def fake_run(*, question, route_decision, answer_text, answer_points, visual_result, retry_count, max_retry):
        assert question == "请审查候选回答"
        assert answer_text == "这是候选回答"
        assert answer_points == ["结论1", "结论2"]
        assert retry_count == 0
        assert max_retry == 1
        return MasterDecision(
            decision=MasterDecisionType.PASS,
            reason="通过",
            missing_items=[],
            retry_from=None,
        )

    monkeypatch.setattr("app.agents.workflow.MasterAgent.run", fake_run)

    result = AnalysisWorkflow._master_agent(
        {
            "user_message": "请审查候选回答",
            "route_decision": _build_route_decision(),
            "answer_draft": AnswerDraft(
                answer="这是候选回答",
                answer_points=["结论1", "结论2"],
            ),
            "retry_count": 0,
            "max_retry": 1,
        }
    )

    assert result["master_decision"].decision == MasterDecisionType.PASS


@pytest.mark.skipif(not DEEPSEEK_API_KEY, reason="未配置 DEEPSEEK_API_KEY，跳过真实大模型测试")
def test_master_agent_with_real_llm():
    visual_result = VisualAgentResult(
        charts=[
            ChartSpec(
                chart_id="chart_bad_review_distribution",
                chart_type=SupportedChartType.PIE,
                title="差评维度分布",
                description="展示差评在不同维度的数量占比",
                x_axis=[],
                series=[
                    ChartSeries(
                        name="差评数量",
                        data=[
                            {"name": "物流", "value": 3},
                            {"name": "质量", "value": 2},
                        ],
                    )
                ],
            )
        ]
    )

    result = MasterAgent.run(
        question="请审查这个关于商品差评的回答是否可以直接交付。",
        route_decision=_build_route_decision(need_visual=True),
        answer_text="该商品差评率约为20%，差评主要集中在物流和质量两个维度，图表也已经生成。",
        answer_points=[
            "差评率约为20%。",
            "差评主要集中在物流和质量两个维度。",
            "已生成图表展示差评维度分布。",
        ],
        visual_result=visual_result,
        retry_count=0,
        max_retry=1,
    )
    print("real_llm_master_agent_result:", flush=True)
    print(result.model_dump_json(indent=2, exclude_none=True), flush=True)

    assert isinstance(result.decision, MasterDecisionType)
    assert isinstance(result.reason, str)
    assert result.reason.strip()


def test_master_agent_fallback_returns_fallback_pass_after_max_retry(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.master_agent.invoke_structured_output", fake_invoke_structured_output)

    result = MasterAgent.run(
        question="请给我图表分析",
        route_decision=_build_route_decision(need_visual=True),
        answer_text="",
        answer_points=[],
        visual_result=VisualAgentResult(charts=[]),
        retry_count=1,
        max_retry=1,
    )

    assert result.decision == MasterDecisionType.FALLBACK_PASS
    assert result.retry_from is None
    assert "visual_result" in result.missing_items
    assert "answer" in result.missing_items
    assert "answer_points" in result.missing_items
