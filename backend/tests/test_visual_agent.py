from __future__ import annotations

import pytest

from app.agents.llm import LLMUnavailableError
from app.agents.visual_agent import VisualAgent
from app.agents.workflow import AnalysisWorkflow
from app.config import DEEPSEEK_API_KEY
from app.schemas.agent_protocol import ChartSeries, ChartSpec, SQLAgentResult, SupportedChartType, VisualAgentResult


def test_visual_agent_returns_empty_when_no_renderable_metrics():
    result = VisualAgent.run(
        question="请画图",
        sql_result_metrics={},
    )

    assert result.charts == []


def test_visual_agent_returns_empty_when_llm_unavailable(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        assert payload["metrics"]["dimension_stats"]["物流"]["avg_score"] == 1.8
        raise LLMUnavailableError("force empty result")

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请画维度对比图",
        sql_result_metrics={
            "dimension_stats": {
                "物流": {"comment_count": 5, "avg_score": 1.8, "bad_review_rate": 0.8, "bad_review_count": 4},
                "售后": {"comment_count": 4, "avg_score": 2.6, "bad_review_rate": 0.5, "bad_review_count": 2},
            }
        },
    )

    assert result.charts == []


def test_visual_agent_discards_fabricated_llm_chart(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        return VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="fake_chart",
                    chart_type=SupportedChartType.BAR,
                    title="差评分布图",
                    description="故意伪造的数据",
                    x_axis=["物流", "售后"],
                    series=[ChartSeries(name="差评数量", data=[999, 888])],
                )
            ]
        )

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请画差评分布图",
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
                    title="差评维度占比图",
                    description="展示各维度差评占比",
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
        question="请画差评占比饼图",
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
    assert result.charts[0].title == "差评维度占比图"
    assert result.charts[0].x_axis == []
    assert result.charts[0].series[0].data == [
        {"name": "物流", "value": 3},
        {"name": "售后", "value": 2},
    ]


def test_visual_agent_keeps_grounded_score_distribution_chart_with_star_labels(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        return VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="score_distribution_bar",
                    chart_type=SupportedChartType.BAR,
                    title="评分分布",
                    description="商品评分分布情况",
                    x_axis=["1星", "2星", "3星", "4星", "5星"],
                    series=[ChartSeries(name="评论数量", data=[0, 20, 20, 80, 80])],
                )
            ]
        )

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请画评分分布图",
        sql_result_metrics={
            "score_distribution": {
                "1": 0,
                "2": 20,
                "3": 20,
                "4": 80,
                "5": 80,
            }
        },
    )

    assert len(result.charts) == 1
    assert result.charts[0].chart_id == "chart_score_distribution"
    assert result.charts[0].x_axis == ["1星", "2星", "3星", "4星", "5星"]
    assert result.charts[0].series[0].data == [0, 20, 20, 80, 80]


def test_visual_agent_keeps_grounded_axis_chart_with_xy_points(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        return VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="score_distribution_bar",
                    chart_type=SupportedChartType.BAR,
                    title="评分分布",
                    description="商品评分分布情况",
                    x_axis=["1", "2", "3", "4", "5"],
                    series=[
                        ChartSeries(
                            name="评论数量",
                            data=[
                                {"x": "1", "y": 0},
                                {"x": "2", "y": 20},
                                {"x": "3", "y": 20},
                                {"x": "4", "y": 80},
                                {"x": "5", "y": 80},
                            ],
                        )
                    ],
                )
            ]
        )

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请画评分分布图",
        sql_result_metrics={
            "score_distribution": {
                "1": 0,
                "2": 20,
                "3": 20,
                "4": 80,
                "5": 80,
            }
        },
    )

    assert len(result.charts) == 1
    assert result.charts[0].chart_id == "chart_score_distribution"
    assert result.charts[0].series[0].data == [0, 20, 20, 80, 80]


def test_visual_agent_keeps_grounded_axis_chart_with_x_axis_y_axis_points(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        return VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="score_distribution_bar",
                    chart_type=SupportedChartType.BAR,
                    title="评分分布",
                    description="商品评分分布情况",
                    x_axis=["1", "2", "3", "4", "5"],
                    series=[
                        ChartSeries(
                            name="评论数量",
                            data=[
                                {"x_axis": "1", "y_axis": 0},
                                {"x_axis": "2", "y_axis": 20},
                                {"x_axis": "3", "y_axis": 20},
                                {"x_axis": "4", "y_axis": 80},
                                {"x_axis": "5", "y_axis": 80},
                            ],
                        )
                    ],
                )
            ]
        )

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请画评分分布图",
        sql_result_metrics={
            "score_distribution": {
                "1": 0,
                "2": 20,
                "3": 20,
                "4": 80,
                "5": 80,
            }
        },
    )

    assert len(result.charts) == 1
    assert result.charts[0].chart_id == "chart_score_distribution"
    assert result.charts[0].series[0].data == [0, 20, 20, 80, 80]


def test_visual_agent_keeps_grounded_score_band_pie_chart(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        return VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="score_band_pie",
                    chart_type=SupportedChartType.PIE,
                    title="评论情感分布",
                    description="好评、中评、差评占比",
                    x_axis=[],
                    series=[
                        ChartSeries(
                            name="评论情感分布",
                            data=[
                                {"name": "好评", "value": 160},
                                {"name": "中评", "value": 20},
                                {"name": "差评", "value": 20},
                            ],
                        )
                    ],
                )
            ]
        )

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请画好中差评占比饼图",
        sql_result_metrics={
            "score_band_distribution": {
                "positive": 160,
                "neutral": 20,
                "negative": 20,
            }
        },
    )

    assert len(result.charts) == 1
    assert result.charts[0].chart_id == "chart_score_band_distribution"
    assert result.charts[0].chart_type == SupportedChartType.PIE
    assert result.charts[0].series[0].data == [
        {"name": "好评", "value": 160},
        {"name": "中评", "value": 20},
        {"name": "差评", "value": 20},
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
                    description="对比各维度差评率和平均评分",
                    x_axis=["物流", "售后"],
                    series=[
                        ChartSeries(name="差评率", data=[0.8, 0.5]),
                        ChartSeries(name="平均评分", data=[1.8, 2.6]),
                    ],
                )
            ]
        )

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请画维度对比图",
        sql_result_metrics={
            "dimension_stats": {
                "物流": {"comment_count": 5, "avg_score": 1.8, "bad_review_rate": 0.8, "bad_review_count": 4},
                "售后": {"comment_count": 4, "avg_score": 2.6, "bad_review_rate": 0.5, "bad_review_count": 2},
            }
        },
    )

    assert len(result.charts) == 1
    assert result.charts[0].chart_id == "chart_dimension_comparison"
    assert result.charts[0].chart_type == SupportedChartType.BAR
    assert result.charts[0].x_axis == ["物流", "售后"]
    assert result.charts[0].series[0].name == "差评率"
    assert result.charts[0].series[0].data == [0.8, 0.5]
    assert result.charts[0].series[1].name == "平均评分"
    assert result.charts[0].series[1].data == [1.8, 2.6]


def test_visual_agent_keeps_grounded_dimension_chart_with_avg_score_alias(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        return VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="dimension_avg_score_radar",
                    chart_type=SupportedChartType.RADAR,
                    title="维度评分雷达图",
                    description="各维度平均分对比",
                    x_axis=["物流", "售后"],
                    series=[ChartSeries(name="平均分", data=[1.8, 2.6])],
                )
            ]
        )

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请画各维度平均分雷达图",
        sql_result_metrics={
            "dimension_stats": {
                "物流": {"comment_count": 5, "avg_score": 1.8, "bad_review_rate": 0.8, "bad_review_count": 4},
                "售后": {"comment_count": 4, "avg_score": 2.6, "bad_review_rate": 0.5, "bad_review_count": 2},
            }
        },
    )

    assert len(result.charts) == 1
    assert result.charts[0].chart_id == "chart_dimension_avg_score"
    assert result.charts[0].chart_type == SupportedChartType.RADAR
    assert result.charts[0].series[0].name == "平均分"
    assert result.charts[0].series[0].data == [1.8, 2.6]


def test_visual_agent_keeps_grounded_dimension_chart_with_xy_points(monkeypatch):
    def fake_invoke_structured_output(*, system_prompt, payload, schema, temperature):
        assert isinstance(system_prompt, str)
        return VisualAgentResult(
            charts=[
                ChartSpec(
                    chart_id="dimension_avg_score_radar",
                    chart_type=SupportedChartType.RADAR,
                    title="维度评分雷达图",
                    description="各维度平均分对比",
                    x_axis=["物流", "售后"],
                    series=[
                        ChartSeries(
                            name="平均评分",
                            data=[
                                {"x": "物流", "y": 1.8},
                                {"x": "售后", "y": 2.6},
                            ],
                        )
                    ],
                )
            ]
        )

    monkeypatch.setattr("app.agents.visual_agent.invoke_structured_output", fake_invoke_structured_output)

    result = VisualAgent.run(
        question="请画各维度平均分雷达图",
        sql_result_metrics={
            "dimension_stats": {
                "物流": {"comment_count": 5, "avg_score": 1.8, "bad_review_rate": 0.8, "bad_review_count": 4},
                "售后": {"comment_count": 4, "avg_score": 2.6, "bad_review_rate": 0.5, "bad_review_count": 2},
            }
        },
    )

    assert len(result.charts) == 1
    assert result.charts[0].chart_id == "chart_dimension_avg_score"
    assert result.charts[0].series[0].data == [1.8, 2.6]


def test_workflow_visual_agent_returns_empty_when_sql_result_missing():
    result = AnalysisWorkflow._visual_agent(
        {
            "user_message": "请画图",
        }
    )

    assert result["visual_result"].charts == []


def test_workflow_visual_agent_returns_empty_when_metrics_not_renderable():
    result = AnalysisWorkflow._visual_agent(
        {
            "user_message": "请画图",
            "sql_result": SQLAgentResult(
                tool_calls=[],
                metrics={"score_summary": {"total_count": 12, "avg_score": 4.2, "low_score_count": 2}},
                description="共有 12 条评论，平均评分 4.2。",
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

    result = VisualAgent.run(
        question="请根据评分分布和差评维度，生成一个评分占比图和一个差评维度对比图。",
        sql_result_metrics=sql_result_metrics,
    )

    assert isinstance(result.charts, list)
    for chart in result.charts:
        assert chart.chart_type in SupportedChartType
        assert isinstance(chart.title, str)
        assert isinstance(chart.x_axis, list)
        assert isinstance(chart.series, list)
