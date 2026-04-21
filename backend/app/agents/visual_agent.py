"""可视化 Agent：基于统计结果生成统一图表 DSL。"""

from __future__ import annotations

from typing import Any

from app.agents.llm import LLMUnavailableError, invoke_structured_output
from app.schemas.agent_protocol import ChartSeries, ChartSpec, SupportedChartType, VisualAgentResult
from app.utils.logger import logger


class VisualAgent:
    """负责把统计指标转换为结构化图表定义。"""
    # 只有这些指标能直接支撑图表生成；其余指标即使存在，也不应驱动 visual_agent。
    RENDERABLE_METRIC_KEYS = {
        "score_summary",
        "score_distribution",
        "bad_review_rate",
        "bad_review_distribution",
        "dimension_stats",
    }
    DIMENSION_SERIES_FIELD_MAP = {
        "平均分": "avg_score",
        "平均评分": "avg_score",
        "差评率": "bad_review_rate",
        "差评数量": "bad_review_count",
        "评论数": "comment_count",
    }

    SYSTEM_PROMPT = """
你是数据可视化专家 visual_agent。

你的职责：
1. 根据用户问题和统计结果自主决定是否适合生成图表，以及生成什么图表。
2. 输出统一的图表 DSL，也就是 VisualAgentResult，而不是原生 ECharts 全量配置。
3. 图表必须直接服务于用户问题，不允许为了展示而堆砌图表。
4. 不得编造统计值，所有 x_axis 和 series.data 都必须来自输入 metrics。

必须严格遵守：
- 输出必须严格符合 VisualAgentResult 结构。
- chart_type 仅可使用：bar, line, pie, scatter, radar, stacked_bar。
- 如果数据不适合生成图表，允许返回空 charts。
- title 和 description 使用简洁中文，且要体现图表用途。
- 你需要结合用户问题判断哪些统计结果值得图表化，而不是机械地把所有指标都画成图。
- 优先选择：
  - 分布类 -> bar / pie
  - 趋势类 -> line
  - 多维对比类 -> bar / stacked_bar / radar
- 不要输出 markdown，不要输出额外解释。
"""

    @staticmethod
    def run(question: str, sql_result_metrics: dict[str, Any]) -> VisualAgentResult:
        """调用大模型选择图表方案，失败时回退到模板化图表生成。"""
        # 第一层保护：如果上游 SQL 根本没有提供可画图的指标，就直接返回空图表。
        if not VisualAgent.has_renderable_metrics(sql_result_metrics):
            logger.info("VisualAgent skipped because no renderable metrics were provided")
            return VisualAgentResult(charts=[])

        # 交给大模型的只是一份“可视化决策上下文”，不是任意作图权限。
        payload = {
            "question": question,
            "metrics": sql_result_metrics,
            "chart_constraints": {
                "allowed_chart_types": [chart.value for chart in SupportedChartType],
                "forbid_data_fabrication": True,
                "output_format": "visual_dsl",
            },
        }
        try:
            # 第一阶段：让模型提出“长什么样”的图表草案。
            result = invoke_structured_output(
                system_prompt=VisualAgent.SYSTEM_PROMPT,
                payload=payload,
                schema=VisualAgentResult,
                temperature=0.2,
            )
            # 第二阶段：对模型草案做二次收敛，只保留能被真实指标支撑的图表。
            return VisualAgent._sanitize_result(
                question=question,
                sql_result_metrics=sql_result_metrics,
                result=result,
            )
        except LLMUnavailableError as exc:
            logger.warning("VisualAgent falling back to template chart generation: {}", exc)
        except Exception as exc:
            logger.exception("VisualAgent structured generation failed, fallback enabled: {}", exc)
        # 第三阶段：模型不可用或输出异常时，使用规则模板生成保守图表。
        return VisualAgent._fallback_run(question=question, sql_result_metrics=sql_result_metrics)

    @staticmethod
    def has_renderable_metrics(sql_result_metrics: dict[str, Any] | None) -> bool:
        """判断当前 SQL 结果中是否存在足以驱动图表生成的指标。"""
        if not isinstance(sql_result_metrics, dict) or not sql_result_metrics:
            return False
        return any(sql_result_metrics.get(metric_key) for metric_key in VisualAgent.RENDERABLE_METRIC_KEYS)

    @staticmethod
    def _fallback_run(question: str, sql_result_metrics: dict[str, Any]) -> VisualAgentResult:
        """在大模型不可用时，按固定模板生成最基础图表。"""
        charts: list[ChartSpec] = []
        normalized_question = question.strip().lower()

        # fallback 的职责不是“尽量多画”，而是基于问题意图只生成最必要的图表。
        if VisualAgent._should_render_score_distribution(question, normalized_question, sql_result_metrics):
            distribution = sql_result_metrics["score_distribution"]
            ordered_keys = sorted(distribution.keys(), key=lambda item: int(item))
            x_axis = [f"{score}星" for score in ordered_keys]
            data = [
                distribution[int(score)]
                if isinstance(next(iter(distribution.keys()), None), int)
                else distribution[score]
                for score in ordered_keys
            ]
            charts.append(
                ChartSpec(
                    chart_id="chart_score_distribution",
                    chart_type=SupportedChartType.BAR,
                    title="评分分布",
                    description="展示 1-5 星评论数量分布",
                    x_axis=x_axis,
                    series=[ChartSeries(name="评论数", data=data)],
                )
            )

        if VisualAgent._should_render_bad_review_distribution(question, normalized_question, sql_result_metrics):
            bad_distribution = sql_result_metrics["bad_review_distribution"]
            ordered_items = sorted(bad_distribution.items(), key=lambda item: item[1], reverse=True)
            charts.append(
                ChartSpec(
                    chart_id="chart_bad_review_distribution",
                    chart_type=SupportedChartType.BAR,
                    title="差评维度分布",
                    description="展示差评在各维度的数量分布",
                    x_axis=[item[0] for item in ordered_items],
                    series=[ChartSeries(name="差评数量", data=[item[1] for item in ordered_items])],
                )
            )

        if VisualAgent._should_render_dimension_stats(question, normalized_question, sql_result_metrics):
            dimension_stats = sql_result_metrics["dimension_stats"]
            ordered_items = sorted(
                dimension_stats.items(),
                key=lambda item: item[1].get("comment_count", 0),
                reverse=True,
            )
            charts.append(
                ChartSpec(
                    chart_id="chart_dimension_avg_score",
                    chart_type=SupportedChartType.BAR,
                    title="维度平均分",
                    description="展示各维度平均评分",
                    x_axis=[item[0] for item in ordered_items],
                    series=[ChartSeries(name="平均分", data=[item[1].get("avg_score", 0) for item in ordered_items])],
                )
            )

        return VisualAgentResult(charts=charts)

    @staticmethod
    def _sanitize_result(
        question: str,
        sql_result_metrics: dict[str, Any],
        result: VisualAgentResult,
    ) -> VisualAgentResult:
        """对大模型输出做二次收敛，只保留可由真实指标支撑的图表。"""
        if not result.charts:
            return VisualAgentResult(charts=[])

        sanitized_charts: list[ChartSpec] = []
        seen_chart_ids: set[str] = set()

        for chart in result.charts:
            # 先过滤结构都不完整的图。
            if not VisualAgent._is_chart_well_formed(chart):
                continue

            grounded_chart = VisualAgent._ground_chart(chart=chart, sql_result_metrics=sql_result_metrics)
            # 只有能被真实指标逐项验证的图表才会被保留；同一个 grounded chart 也不允许重复收录。
            if grounded_chart is None or grounded_chart.chart_id in seen_chart_ids:
                continue

            seen_chart_ids.add(grounded_chart.chart_id)
            sanitized_charts.append(grounded_chart)

        return VisualAgentResult(charts=sanitized_charts)

    @staticmethod
    def _is_chart_well_formed(chart: ChartSpec) -> bool:
        """校验图表基础结构，避免接受长度不一致或空数据图表。"""
        if not chart.series:
            return False
        if chart.chart_type == SupportedChartType.PIE:
            if len(chart.series) != 1 or not chart.series[0].data:
                return False
            return all(
                isinstance(item, dict) and item.get("name") is not None and item.get("value") is not None
                for item in chart.series[0].data
            )
        if not chart.x_axis:
            return False
        expected_length = len(chart.x_axis)
        if expected_length <= 0:
            return False
        return all(len(series.data) == expected_length for series in chart.series)

    @staticmethod
    def _ground_chart(chart: ChartSpec, sql_result_metrics: dict[str, Any]) -> ChartSpec | None:
        """把 LLM 图表绑定到真实指标；绑定失败说明这张图的数据不可信。"""
        if chart.chart_type == SupportedChartType.PIE:
            return (
                VisualAgent._ground_distribution_pie_chart(
                    chart=chart,
                    metric_name="bad_review_distribution",
                    chart_id="chart_bad_review_distribution",
                    sql_result_metrics=sql_result_metrics,
                )
                or VisualAgent._ground_distribution_pie_chart(
                    chart=chart,
                    metric_name="score_distribution",
                    chart_id="chart_score_distribution",
                    sql_result_metrics=sql_result_metrics,
                )
            )

        return (
            VisualAgent._ground_distribution_axis_chart(
                chart=chart,
                metric_name="bad_review_distribution",
                chart_id="chart_bad_review_distribution",
                sql_result_metrics=sql_result_metrics,
            )
            or VisualAgent._ground_distribution_axis_chart(
                chart=chart,
                metric_name="score_distribution",
                chart_id="chart_score_distribution",
                sql_result_metrics=sql_result_metrics,
            )
            or VisualAgent._ground_dimension_stats_chart(chart=chart, sql_result_metrics=sql_result_metrics)
        )

    @staticmethod
    def _ground_distribution_axis_chart(
        chart: ChartSpec,
        metric_name: str,
        chart_id: str,
        sql_result_metrics: dict[str, Any],
    ) -> ChartSpec | None:
        """校验柱状/折线等按坐标轴展开的分布图是否与真实分布一致。"""
        distribution = sql_result_metrics.get(metric_name)
        if not isinstance(distribution, dict) or not chart.x_axis or len(chart.series) != 1:
            return None

        expected_values: list[Any] = []
        for label in chart.x_axis:
            value = VisualAgent._lookup_distribution_value(distribution, label)
            if value is None:
                return None
            expected_values.append(value)

        if not VisualAgent._numeric_sequence_matches(chart.series[0].data, expected_values):
            return None

        return ChartSpec(
            chart_id=chart_id,
            chart_type=chart.chart_type,
            title=chart.title,
            description=chart.description,
            x_axis=list(chart.x_axis),
            series=[ChartSeries(name=chart.series[0].name, data=expected_values)],
        )

    @staticmethod
    def _ground_distribution_pie_chart(
        chart: ChartSpec,
        metric_name: str,
        chart_id: str,
        sql_result_metrics: dict[str, Any],
    ) -> ChartSpec | None:
        """校验饼图的 name/value 数据是否与真实分布一致。"""
        distribution = sql_result_metrics.get(metric_name)
        if not isinstance(distribution, dict) or len(chart.series) != 1:
            return None

        grounded_points: list[dict[str, Any]] = []
        for item in chart.series[0].data:
            label = item.get("name") if isinstance(item, dict) else None
            actual_value = item.get("value") if isinstance(item, dict) else None
            if label is None:
                return None
            expected_value = VisualAgent._lookup_distribution_value(distribution, label)
            if expected_value is None or not VisualAgent._numeric_matches(actual_value, expected_value):
                return None
            grounded_points.append({"name": str(label), "value": expected_value})

        return ChartSpec(
            chart_id=chart_id,
            chart_type=chart.chart_type,
            title=chart.title,
            description=chart.description,
            x_axis=[],
            series=[ChartSeries(name=chart.series[0].name, data=grounded_points)],
        )

    @staticmethod
    def _ground_dimension_stats_chart(chart: ChartSpec, sql_result_metrics: dict[str, Any]) -> ChartSpec | None:
        """校验多维对比图是否完全由 dimension_stats 推导而来。"""
        dimension_stats = sql_result_metrics.get("dimension_stats")
        if not isinstance(dimension_stats, dict) or not chart.x_axis or not chart.series:
            return None

        grounded_series: list[ChartSeries] = []
        for series in chart.series:
            metric_field = VisualAgent.DIMENSION_SERIES_FIELD_MAP.get(series.name)
            if metric_field is None:
                return None

            expected_values: list[Any] = []
            for dimension in chart.x_axis:
                dimension_value = dimension_stats.get(str(dimension))
                if not isinstance(dimension_value, dict) or metric_field not in dimension_value:
                    return None
                expected_values.append(dimension_value[metric_field])

            if not VisualAgent._numeric_sequence_matches(series.data, expected_values):
                return None
            grounded_series.append(ChartSeries(name=series.name, data=expected_values))

        chart_id = "chart_dimension_avg_score" if len(grounded_series) == 1 and grounded_series[0].name in {"平均分", "平均评分"} else "chart_dimension_comparison"
        return ChartSpec(
            chart_id=chart_id,
            chart_type=chart.chart_type,
            title=chart.title,
            description=chart.description,
            x_axis=list(chart.x_axis),
            series=grounded_series,
        )

    @staticmethod
    def _lookup_distribution_value(distribution: dict[str, Any], label: Any) -> Any | None:
        """兼容 int/str 键差异，查找分布图中的真实值。"""
        if label in distribution:
            return distribution[label]
        label_str = str(label)
        if label_str in distribution:
            return distribution[label_str]
        if label_str.endswith("星"):
            star_value = label_str[:-1]
            if star_value.isdigit():
                if int(star_value) in distribution:
                    return distribution[int(star_value)]
                if star_value in distribution:
                    return distribution[star_value]
        return None

    @staticmethod
    def _numeric_sequence_matches(actual_values: list[Any], expected_values: list[Any]) -> bool:
        """逐项比较数值序列，允许轻微浮点误差。"""
        if len(actual_values) != len(expected_values):
            return False
        return all(
            VisualAgent._numeric_matches(actual, expected)
            for actual, expected in zip(actual_values, expected_values, strict=False)
        )

    @staticmethod
    def _numeric_matches(actual: Any, expected: Any) -> bool:
        """比较单个数值，允许模型输出做轻微四舍五入。"""
        try:
            return abs(float(actual) - float(expected)) <= 1e-4
        except (TypeError, ValueError):
            return actual == expected

    @staticmethod
    def _should_render_score_distribution(
        question: str,
        normalized_question: str,
        sql_result_metrics: dict[str, Any],
    ) -> bool:
        # 没有数据时直接不画；有数据时再看问题是否真的在问“评分分布”。
        if not sql_result_metrics.get("score_distribution"):
            return False
        return any(
            keyword in question or keyword in normalized_question
            for keyword in ("评分", "score", "rating", "分布", "可视化", "图", "图表")
        )

    @staticmethod
    def _should_render_bad_review_distribution(
        question: str,
        normalized_question: str,
        sql_result_metrics: dict[str, Any],
    ) -> bool:
        if not sql_result_metrics.get("bad_review_distribution"):
            return False
        return any(
            keyword in question or keyword in normalized_question
            for keyword in ("差评", "bad review", "negative review", "分布", "可视化", "图", "图表")
        )

    @staticmethod
    def _should_render_dimension_stats(
        question: str,
        normalized_question: str,
        sql_result_metrics: dict[str, Any],
    ) -> bool:
        if not sql_result_metrics.get("dimension_stats"):
            return False
        return any(
            keyword in question or keyword in normalized_question
            for keyword in ("维度", "物流", "质量", "价格", "售后", "性能", "对比", "可视化", "图", "图表")
        )
