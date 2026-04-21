from __future__ import annotations

import pytest

from app.agents.llm import LLMUnavailableError
from app.agents.visual_agent import VisualAgent
from app.agents.workflow import AnalysisWorkflow
from app.config import DEEPSEEK_API_KEY
from app.schemas.agent_protocol import ChartSeries, ChartSpec, SQLAgentResult, SupportedChartType, VisualAgentResult


def test_visual_agent_returns_empty_when_no_renderable_metrics():
    result = VisualAgent.run(
        question="请做可视化",
        sql_result_metrics={},
    )

    assert result.charts == []


def test_visual_agent_fallback_uses_bar_for_dimension_stats(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        assert payload["metrics"]["dimension_stats"]["物流"]["avg_score"] == 1.8
        raise LLMUnavailableError("force fallback")

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请把各维度表现做成图表",
        sql_result_metrics={
            "dimension_stats": {
                "物流": {"comment_count": 5, "avg_score": 1.8, "bad_review_rate": 0.8, "bad_review_count": 4},
                "质量": {"comment_count": 4, "avg_score": 2.6, "bad_review_rate": 0.5, "bad_review_count": 2},
            }
        },
    )

    assert len(result.charts) == 1
    assert result.charts[0].chart_id == "chart_dimension_avg_score"
    assert result.charts[0].chart_type == SupportedChartType.BAR
    assert result.charts[0].x_axis == ["物流", "质量"]
    assert result.charts[0].series[0].data == [1.8, 2.6]


def test_visual_agent_discards_fabricated_llm_chart(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        return VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="fake_chart",
                    chart_type=SupportedChartType.BAR,
                    title="伪造差评图",
                    description="这张图的数据是编的",
                    x_axis=["物流", "售后"],
                    series=[ChartSeries(name="差评数量", data=[999, 888])],
                )
            ]
        )

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请把差评分布可视化",
        sql_result_metrics={
            "bad_review_distribution": {
                "物流": 3,
                "售后": 2,
            }
        },
    )

    assert result.charts == []


def test_visual_agent_keeps_grounded_llm_chart_and_reuses_real_metric_data(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        return VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="custom_chart_id",
                    chart_type=SupportedChartType.PIE,
                    title="模型生成的差评构成图",
                    description="使用真实差评分布数据",
                    x_axis=[],
                    series=[
                        ChartSeries(
                            name="差评数量",
                            data=[
                                {"name": "物流", "value": 3},
                                {"name": "售后", "value": 2},
                            ],
                        )
                    ],
                )
            ]
        )

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请把差评分布可视化",
        sql_result_metrics={
            "bad_review_distribution": {
                "物流": 3,
                "售后": 2,
            }
        },
    )

    assert len(result.charts) == 1
    assert result.charts[0].chart_id == "chart_bad_review_distribution"
    assert result.charts[0].chart_type == SupportedChartType.PIE
    assert result.charts[0].title == "模型生成的差评构成图"
    assert result.charts[0].x_axis == []
    assert result.charts[0].series[0].data == [
        {"name": "物流", "value": 3},
        {"name": "售后", "value": 2},
    ]


def test_visual_agent_keeps_grounded_dimension_comparison_chart(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        return VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="dimension_comparison_bar",
                    chart_type=SupportedChartType.BAR,
                    title="维度表现对比",
                    description="各维度差评率与平均评分对比",
                    x_axis=["物流", "质量"],
                    series=[
                        ChartSeries(name="差评率", data=[0.8, 0.5]),
                        ChartSeries(name="平均评分", data=[1.8, 2.6]),
                    ],
                )
            ]
        )

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请把各维度表现做成图表",
        sql_result_metrics={
            "dimension_stats": {
                "物流": {"comment_count": 5, "avg_score": 1.8, "bad_review_rate": 0.8, "bad_review_count": 4},
                "质量": {"comment_count": 4, "avg_score": 2.6, "bad_review_rate": 0.5, "bad_review_count": 2},
            }
        },
    )

    assert len(result.charts) == 1
    assert result.charts[0].chart_id == "chart_dimension_comparison"
    assert result.charts[0].chart_type == SupportedChartType.BAR
    assert result.charts[0].x_axis == ["物流", "质量"]
    assert result.charts[0].series[0].name == "差评率"
    assert result.charts[0].series[0].data == [0.8, 0.5]
    assert result.charts[0].series[1].name == "平均评分"
    assert result.charts[0].series[1].data == [1.8, 2.6]


def test_workflow_visual_agent_returns_empty_when_sql_result_missing():
    result = AnalysisWorkflow._visual_agent(
        {
            "user_message": "请做可视化",
        }
    )

    assert result["visual_result"].charts == []


def test_workflow_visual_agent_returns_empty_when_metrics_not_renderable():
    result = AnalysisWorkflow._visual_agent(
        {
            "user_message": "请做可视化",
            "sql_result": SQLAgentResult(
                tool_calls=[],
                metrics={"score_summary": {"total_count": 12, "avg_score": 4.2, "low_score_count": 2}},
                description="共有 12 条评论，平均分 4.2。",
            ),
        }
    )

    assert result["visual_result"].charts == []


@pytest.mark.skipif(not DEEPSEEK_API_KEY, reason="DEEPSEEK_API_KEY 未配置，跳过真实大模型测试")
def test_visual_agent_with_real_llm():
    sql_result_metrics = {
        "score_distribution": {
            1: 2,
            2: 4,
            3: 6,
            4: 10,
            5: 8,
        },
        "bad_review_distribution": {
            "物流": 5,
            "质量": 3,
            "售后": 2,
        },
        "dimension_stats": {
            "物流": {"comment_count": 8, "avg_score": 2.0, "bad_review_rate": 0.625, "bad_review_count": 5},
            "质量": {"comment_count": 7, "avg_score": 2.6, "bad_review_rate": 0.4286, "bad_review_count": 3},
            "售后": {"comment_count": 5, "avg_score": 3.0, "bad_review_rate": 0.4, "bad_review_count": 2},
        },
    }

    original_invoke = VisualAgent.run.__globals__["invoke_structured_output"]

    def traced_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        raw_result = original_invoke(
            system_prompt=system_prompt,
            payload=payload,
            schema=schema,
            temperature=temperature,
        )
        print("raw_llm_visual_agent_result:", flush=True)
        print(raw_result.model_dump_json(indent=2), flush=True)
        return raw_result

    VisualAgent.run.__globals__["invoke_structured_output"] = traced_invoke_structured_output
    try:
        result = VisualAgent.run(
            question="请根据这些统计结果生成最合适的可视化图表，重点展示差评分布和维度对比",
            sql_result_metrics=sql_result_metrics,
        )
    finally:
        VisualAgent.run.__globals__["invoke_structured_output"] = original_invoke

    print("sanitized_visual_agent_result:", flush=True)
    print(result.model_dump_json(indent=2), flush=True)

    assert isinstance(result.charts, list)
    for chart in result.charts:
        assert chart.chart_type in SupportedChartType
        assert isinstance(chart.title, str)
        assert isinstance(chart.x_axis, list)
        assert isinstance(chart.series, list)
