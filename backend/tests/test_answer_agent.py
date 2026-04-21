from __future__ import annotations

import pytest

from app.agents.answer_agent import AnswerAgent
from app.agents.llm import LLMUnavailableError
from app.agents.workflow import AnalysisWorkflow
from app.config import DEEPSEEK_API_KEY
from app.schemas.agent_protocol import (
    AnswerDraft,
    ChartSeries,
    ChartSpec,
    RAGAgentResult,
    ResponseStyle,
    RouteDecision,
    SQLAgentResult,
    SupportedChartType,
    VisualAgentResult,
)


def _build_route_decision(response_style: ResponseStyle = ResponseStyle.PROFESSIONAL_ANALYSIS) -> RouteDecision:
    return RouteDecision(
        need_sql=True,
        need_rag=False,
        need_visual=False,
        analysis_targets=["bad_review_rate"],
        response_style=response_style,
        reason="测试 answer_agent 使用",
    )


def test_answer_agent_run_passes_question_and_style_to_llm(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        assert schema is AnswerDraft
        assert temperature == 0.2
        assert payload["question"] == "请直接总结当前分析结果"
        assert payload["route_decision"]["response_style"] == ResponseStyle.BRIEF_ANSWER.value
        return AnswerDraft(
            answer="这是简短回答",
            answer_points=["关键结论"],
        )

    monkeypatch.setattr("app.agents.answer_agent.invoke_structured_output", fake_invoke_structured_output)

    result = AnswerAgent.run(
        question="请直接总结当前分析结果",
        route_decision=_build_route_decision(ResponseStyle.BRIEF_ANSWER),
    )

    assert result.answer == "这是简短回答"
    assert result.answer_points == ["关键结论"]


def test_answer_agent_fallback_brief_answer_uses_first_two_points(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.answer_agent.invoke_structured_output", fake_invoke_structured_output)

    result = AnswerAgent.run(
        question="请总结这个商品的差评情况",
        route_decision=_build_route_decision(ResponseStyle.BRIEF_ANSWER),
        sql_result=SQLAgentResult(
            tool_calls=[],
            metrics={"bad_review_rate": 0.4},
            description="该商品差评率约为40%。",
        ),
        rag_result=RAGAgentResult(
            queries=[],
            evidence=[],
            insight="评论语义显示问题主要集中在物流和质量。",
        ),
        visual_result=VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="chart_bad_review_distribution",
                    chart_type=SupportedChartType.BAR,
                    title="差评维度分布",
                    description="展示差评在不同维度上的分布。",
                    x_axis=["物流", "质量"],
                    series=[ChartSeries(name="差评数量", data=[3, 2])],
                )
            ]
        ),
    )

    assert result.answer == "该商品差评率约为40%。；评论语义显示问题主要集中在物流和质量。"
    assert result.answer_points == [
        "该商品差评率约为40%。",
        "评论语义显示问题主要集中在物流和质量。",
        "已生成1个图表，包括差评维度分布，可结合图表进一步查看。",
    ]


def test_answer_agent_fallback_deduplicates_points_and_mentions_chart_titles(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.answer_agent.invoke_structured_output", fake_invoke_structured_output)

    repeated_point = "评论语义显示问题主要集中在物流。"
    result = AnswerAgent.run(
        question="请分析用户差评原因",
        route_decision=_build_route_decision(ResponseStyle.PROFESSIONAL_ANALYSIS),
        sql_result=SQLAgentResult(
            tool_calls=[],
            metrics={},
            description=repeated_point,
        ),
        rag_result=RAGAgentResult(
            queries=[],
            evidence=[],
            insight=repeated_point,
        ),
        visual_result=VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="chart_1",
                    chart_type=SupportedChartType.PIE,
                    title="差评来源分布",
                    description="",
                    x_axis=[],
                    series=[ChartSeries(name="差评数量", data=[{"name": "物流", "value": 3}])],
                ),
                ChartSpec(
                    chart_id="chart_2",
                    chart_type=SupportedChartType.BAR,
                    title="差评维度分布",
                    description="",
                    x_axis=["物流"],
                    series=[ChartSeries(name="差评数量", data=[3])],
                ),
            ]
        ),
    )

    assert result.answer_points == [
        "评论语义显示问题主要集中在物流。",
        "已生成2个图表，包括差评来源分布、差评维度分布，可结合图表进一步查看。",
    ]
    assert result.answer.startswith("针对“请分析用户差评原因”，结合当前分析结果，")


def test_answer_agent_fallback_prefers_rag_insight_points(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.answer_agent.invoke_structured_output", fake_invoke_structured_output)

    result = AnswerAgent.run(
        question="请分析差评原因",
        route_decision=_build_route_decision(ResponseStyle.PROFESSIONAL_ANALYSIS),
        rag_result=RAGAgentResult(
            queries=[],
            evidence=[],
            insight="评论语义显示问题主要集中在物流。",
            insight_points=["物流吐槽最集中。", "典型抱怨是配送慢。"],
        ),
    )

    assert result.answer_points == [
        "物流吐槽最集中。",
        "典型抱怨是配送慢。",
    ]


def test_workflow_answer_agent_passes_user_message(monkeypatch):
    route_decision = _build_route_decision()

    def fake_run(*, question, route_decision, sql_result, rag_result, visual_result):
        assert question == "请生成最终回答"
        assert route_decision.response_style == ResponseStyle.PROFESSIONAL_ANALYSIS
        assert sql_result is None
        assert rag_result is None
        assert visual_result is None
        return AnswerDraft(answer="好的回答", answer_points=["关键点"])

    monkeypatch.setattr("app.agents.workflow.AnswerAgent.run", fake_run)

    result = AnalysisWorkflow._answer_agent(
        {
            "user_message": "请生成最终回答",
            "route_decision": route_decision,
        }
    )

    assert result["answer_draft"].answer == "好的回答"
    assert result["answer_draft"].answer_points == ["关键点"]


@pytest.mark.skipif(not DEEPSEEK_API_KEY, reason="DEEPSEEK_API_KEY 未配置，跳过真实大模型测试")
def test_answer_agent_with_real_llm():
    route_decision = RouteDecision(
        need_sql=True,
        need_rag=True,
        need_visual=True,
        analysis_targets=["bad_review_rate", "bad_review_distribution"],
        response_style=ResponseStyle.PROFESSIONAL_ANALYSIS,
        reason="用户要求分析差评并给出图表说明。",
    )
    sql_result = SQLAgentResult(
        tool_calls=[
            {"tool": "get_bad_review_rate", "args": {"product_id": 88}},
            {"tool": "get_bad_review_distribution", "args": {"product_id": 88}},
        ],
        metrics={
            "bad_review_rate": 0.2,
            "bad_review_distribution": {
                "物流": 3,
                "质量": 2,
            },
        },
        description="该商品差评率约为20%，差评主要集中在物流和质量维度。",
    )
    rag_result = RAGAgentResult(
        queries=["商品差评原因", "物流相关差评"],
        evidence=[
            {
                "content": "物流速度太慢，等了很久才到。",
                "dimension": "物流",
                "score": 1,
                "similarity": 0.91,
            },
            {
                "content": "做工一般，边角处理不够细致。",
                "dimension": "质量",
                "score": 2,
                "similarity": 0.88,
            },
        ],
        insight="评论语义显示，差评原因主要集中在物流时效和产品做工。",
        insight_points=[
            "物流相关差评较集中。",
            "典型原因是配送时效慢和做工不够细致。",
        ],
    )
    visual_result = VisualAgentResult(
        charts=[
            ChartSpec(
                chart_id="chart_bad_review_distribution",
                chart_type=SupportedChartType.PIE,
                title="差评维度分布",
                description="展示差评在不同维度上的占比。",
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

    result = AnswerAgent.run(
        question="请总结这个商品的差评情况，并结合图表说明。",
        route_decision=route_decision,
        sql_result=sql_result,
        rag_result=rag_result,
        visual_result=visual_result,
    )
    print("real_llm_answer_agent_result:", flush=True)
    print(result.model_dump_json(indent=2, exclude_none=True), flush=True)

    assert isinstance(result.answer, str)
    assert result.answer.strip()
    assert isinstance(result.answer_points, list)
    assert len(result.answer_points) >= 1
