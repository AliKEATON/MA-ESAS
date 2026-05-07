"""可视化 Agent：仅依赖大模型基于 SQL 指标生成图表 DSL。"""

from __future__ import annotations

from typing import Any

from app.agents.llm import LLMUnavailableError, invoke_structured_output
from app.schemas.agent_protocol import ChartSeries, ChartSpec, SupportedChartType, VisualAgentResult
from app.utils.logger import logger


class VisualAgent:
    """将结构化 SQL 指标转换为经过落地校验的图表定义。"""

    RENDERABLE_METRIC_KEYS = {
        "score_summary",
        "score_distribution",
        "bad_review_rate",
        "score_band_distribution",
        "bad_review_distribution",
        "dimension_stats",
        "monthly_score_trend",
        "dimension_coverage",
    }
    DIMENSION_SERIES_FIELD_MAP = {
        "平均评分": "avg_score",
        "评分均值": "avg_score",
        "平均分": "avg_score",
        "差评率": "bad_review_rate",
        "差评数量": "bad_review_count",
        "差评数": "bad_review_count",
        "评论数量": "comment_count",
        "评论数": "comment_count",
    }
    AVG_SCORE_SERIES_NAMES = {"平均评分", "评分均值", "平均分"}

    SYSTEM_PROMPT = """
你是商品评论分析工作流中的 visual_agent。

你的职责：
1. 读取用户问题和已经计算好的 SQL 指标。
2. 只基于真实指标生成图表 DSL，输出必须符合 VisualAgentResult 协议。
3. 不要编造任何数据，也不要输出协议之外的字段。
4. 图表中的 x_axis、series.data、饼图 name/value 都必须直接来自 metrics。

输出要求：
- 只返回符合 VisualAgentResult 的结构化结果。
- chart_type 只能使用：bar、line、pie、scatter、radar、stacked_bar。
- 如果没有必要画图，可以返回空 charts。
- title 和 description 要简洁，直接描述图表含义。

选图建议：
- 占比、构成、评分分布：优先使用 pie 或 bar。
- 趋势：使用 line。
- 维度对比：可使用 bar、stacked_bar 或 radar。

禁止事项：
- 不要输出 markdown。
- 不要解释推理过程。
- 不要猜测缺失数据。
"""

    @staticmethod
    def run(question: str, sql_result_metrics: dict[str, Any]) -> VisualAgentResult:
        """调用大模型生成图表，失败时直接返回空图表。"""
        if not VisualAgent.has_renderable_metrics(sql_result_metrics):
            logger.info("VisualAgent skipped because no renderable metrics were provided")
            return VisualAgentResult(charts=[])

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
            result = invoke_structured_output(
                system_prompt=VisualAgent.SYSTEM_PROMPT,
                payload=payload,
                schema=VisualAgentResult,
                temperature=0.2,
            )
            return VisualAgent._sanitize_result(sql_result_metrics=sql_result_metrics, result=result)
        except LLMUnavailableError as exc:
            logger.warning("VisualAgent skipped because LLM is unavailable: {}", exc)
        except Exception as exc:
            logger.exception("VisualAgent structured generation failed, charts skipped: {}", exc)
        return VisualAgentResult(charts=[])

    @staticmethod
    def has_renderable_metrics(sql_result_metrics: dict[str, Any] | None) -> bool:
        """判断当前 SQL 指标里是否存在可驱动图表生成的字段。"""
        if not isinstance(sql_result_metrics, dict) or not sql_result_metrics:
            return False
        return any(sql_result_metrics.get(metric_key) for metric_key in VisualAgent.RENDERABLE_METRIC_KEYS)

    @staticmethod
    def _sanitize_result(*, sql_result_metrics: dict[str, Any], result: VisualAgentResult) -> VisualAgentResult:
        """只保留结构合法且能够落地到真实指标的图表。"""
        if not result.charts:
            return VisualAgentResult(charts=[])

        sanitized_charts: list[ChartSpec] = []
        seen_chart_ids: set[str] = set()

        for chart in result.charts:
            # 第一步先做纯结构层校验，尽早过滤掉明显不完整的图表。
            # 例如：没有 series、饼图缺少 name/value、轴图没有 x_axis 等。
            if not VisualAgent._is_chart_well_formed(chart):
                continue

            # 第二步再做“数据落地”校验：
            # 要求图表里出现的标签、数值必须能在 SQL 指标里一一找到。
            # 这里只要任意一个点对不上，就直接丢弃整张图，避免前端展示伪造数据。
            grounded_chart = VisualAgent._ground_chart(chart=chart, sql_result_metrics=sql_result_metrics)
            if grounded_chart is None or grounded_chart.chart_id in seen_chart_ids:
                continue

            # 同一种指标图只保留一张，避免模型输出重复图表。
            seen_chart_ids.add(grounded_chart.chart_id)
            sanitized_charts.append(grounded_chart)

        return VisualAgentResult(charts=sanitized_charts)

    @staticmethod
    def _is_chart_well_formed(chart: ChartSpec) -> bool:
        """在落地校验前，先检查图表结构是否完整。"""
        if not chart.series:
            return False
        if chart.chart_type == SupportedChartType.PIE:
            # 饼图必须只有一个主序列，并且每个数据点都带 name/value。
            if len(chart.series) != 1 or not chart.series[0].data:
                return False
            return all(
                isinstance(item, dict) and item.get("name") is not None and item.get("value") is not None
                for item in chart.series[0].data
            )
        # 非饼图统一按“轴图”处理，必须给出 x_axis。
        if not chart.x_axis:
            return False
        expected_length = len(chart.x_axis)
        if expected_length <= 0:
            return False
        # 每个系列的数据长度都必须和横轴长度一致，否则前端无法稳定渲染。
        # 这里允许模型输出纯数值数组，也允许输出 [{x, y}] 的点结构。
        return all(len(series.data) == expected_length for series in chart.series)

    @staticmethod
    def _ground_chart(chart: ChartSpec, sql_result_metrics: dict[str, Any]) -> ChartSpec | None:
        """将大模型生成的图表定义映射到真实 SQL 指标。"""
        if chart.chart_type == SupportedChartType.PIE:
            # 饼图只允许来自“分布类指标”，当前支持：
            # 1. 差评维度分布
            # 2. 评分分布
            # 3. 好中差评占比
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
                or VisualAgent._ground_distribution_pie_chart(
                    chart=chart,
                    metric_name="score_band_distribution",
                    chart_id="chart_score_band_distribution",
                    sql_result_metrics=sql_result_metrics,
                )
            )

        # 轴图优先尝试映射到分布类指标；如果对不上，再尝试映射到维度统计。
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
            or VisualAgent._ground_distribution_axis_chart(
                chart=chart,
                metric_name="score_band_distribution",
                chart_id="chart_score_band_distribution",
                sql_result_metrics=sql_result_metrics,
            )
            or VisualAgent._ground_distribution_axis_chart(
                chart=chart,
                metric_name="dimension_coverage",
                chart_id="chart_dimension_coverage",
                sql_result_metrics=sql_result_metrics,
            )
            or VisualAgent._ground_monthly_trend_chart(
                chart=chart,
                sql_result_metrics=sql_result_metrics,
            )
            or VisualAgent._ground_dimension_stats_chart(chart=chart, sql_result_metrics=sql_result_metrics)
        )

    @staticmethod
    def _ground_distribution_axis_chart(
        *,
        chart: ChartSpec,
        metric_name: str,
        chart_id: str,
        sql_result_metrics: dict[str, Any],
    ) -> ChartSpec | None:
        """校验并落地基于坐标轴的分布图。"""
        distribution = sql_result_metrics.get(metric_name)
        if not isinstance(distribution, dict) or not chart.x_axis or len(chart.series) != 1:
            return None

        expected_values: list[Any] = []
        for label in chart.x_axis:
            # x_axis 上的每一个标签都必须能在真实分布指标里查到对应值。
            # 这里允许模型输出 "1分" / "1" / 1 这种轻微格式差异。
            value = VisualAgent._lookup_distribution_value(distribution, label)
            if value is None:
                return None
            expected_values.append(value)

        # 如果模型输出的序列值和真实指标不一致，则整张图判定为无效。
        actual_values = VisualAgent._extract_series_values(chart.series[0].data)
        if actual_values is None or not VisualAgent._numeric_sequence_matches(actual_values, expected_values):
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
        *,
        chart: ChartSpec,
        metric_name: str,
        chart_id: str,
        sql_result_metrics: dict[str, Any],
    ) -> ChartSpec | None:
        """校验并落地饼图的 name/value 数据点。"""
        distribution = sql_result_metrics.get(metric_name)
        if not isinstance(distribution, dict) or len(chart.series) != 1:
            return None

        grounded_points: list[dict[str, Any]] = []
        for item in chart.series[0].data:
            label = item.get("name") if isinstance(item, dict) else None
            actual_value = item.get("value") if isinstance(item, dict) else None
            if label is None:
                return None
            # 饼图每个扇区都必须能映射到真实指标，并且 value 也必须和真实值一致。
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
    def _ground_dimension_stats_chart(*, chart: ChartSpec, sql_result_metrics: dict[str, Any]) -> ChartSpec | None:
        """校验并落地基于 dimension_stats 的维度对比图。"""
        dimension_stats = sql_result_metrics.get("dimension_stats")
        if not isinstance(dimension_stats, dict) or not chart.x_axis or not chart.series:
            return None

        grounded_series: list[ChartSeries] = []
        for series in chart.series:
            # 先把模型输出的系列名称映射到内部真实字段。
            # 例如“平均评分” -> avg_score，“差评率” -> bad_review_rate。
            metric_field = VisualAgent.DIMENSION_SERIES_FIELD_MAP.get(series.name)
            if metric_field is None:
                return None

            expected_values: list[Any] = []
            for dimension in chart.x_axis:
                # 每个维度都必须存在，且必须能找到对应字段值。
                dimension_value = dimension_stats.get(str(dimension))
                if not isinstance(dimension_value, dict) or metric_field not in dimension_value:
                    return None
                expected_values.append(dimension_value[metric_field])

            # 系列里的数值必须和真实 dimension_stats 一致。
            actual_values = VisualAgent._extract_series_values(series.data)
            if actual_values is None or not VisualAgent._numeric_sequence_matches(actual_values, expected_values):
                return None
            grounded_series.append(ChartSeries(name=series.name, data=expected_values))

        # 单系列平均分图和多系列维度对比图，使用不同 chart_id，便于前端和日志区分。
        chart_id = (
            "chart_dimension_avg_score"
            if len(grounded_series) == 1 and grounded_series[0].name in VisualAgent.AVG_SCORE_SERIES_NAMES
            else "chart_dimension_comparison"
        )
        return ChartSpec(
            chart_id=chart_id,
            chart_type=chart.chart_type,
            title=chart.title,
            description=chart.description,
            x_axis=list(chart.x_axis),
            series=grounded_series,
        )

    @staticmethod
    def _ground_monthly_trend_chart(*, chart: ChartSpec, sql_result_metrics: dict[str, Any]) -> ChartSpec | None:
        """校验并落地按月趋势图。"""
        monthly_trend = sql_result_metrics.get("monthly_score_trend")
        if not isinstance(monthly_trend, list) or not chart.x_axis or not chart.series:
            return None

        monthly_lookup = {
            str(item.get("month")): item
            for item in monthly_trend
            if isinstance(item, dict) and item.get("month") is not None
        }
        if not monthly_lookup:
            return None

        series_field_map = {
            "评论数量": "comment_count",
            "平均评分": "avg_score",
            "评分均值": "avg_score",
            "差评率": "bad_review_rate",
            "差评数量": "bad_review_count",
        }

        grounded_series: list[ChartSeries] = []
        for series in chart.series:
            metric_field = series_field_map.get(series.name)
            if metric_field is None:
                return None

            expected_values: list[Any] = []
            for month in chart.x_axis:
                month_row = monthly_lookup.get(str(month))
                if not isinstance(month_row, dict) or metric_field not in month_row:
                    return None
                expected_values.append(month_row[metric_field])

            actual_values = VisualAgent._extract_series_values(series.data)
            if actual_values is None or not VisualAgent._numeric_sequence_matches(actual_values, expected_values):
                return None
            grounded_series.append(ChartSeries(name=series.name, data=expected_values))

        return ChartSpec(
            chart_id="chart_monthly_score_trend",
            chart_type=chart.chart_type,
            title=chart.title,
            description=chart.description,
            x_axis=list(chart.x_axis),
            series=grounded_series,
        )

    @staticmethod
    def _lookup_distribution_value(distribution: dict[str, Any], label: Any) -> Any | None:
        """在容忍字符串/整数标签差异的前提下查找分布值。"""
        label_str = str(label)
        candidate_labels: list[Any] = [label, label_str]

        # 评分分布场景下，模型可能把 1 写成 "1分" 或 "1星"，
        # 这里统一做格式归一化，避免因为展示形式不同而误判。
        if label_str.endswith(("分", "星")):
            score_value = label_str[:-1]
            if score_value.isdigit():
                candidate_labels.extend([int(score_value), score_value])

        # 好中差评占比场景下，大模型更可能输出中文标签，而真实指标使用英文键。
        score_band_aliases = {
            "好评": "positive",
            "中评": "neutral",
            "差评": "negative",
        }
        if label_str in score_band_aliases:
            candidate_labels.append(score_band_aliases[label_str])

        for candidate in candidate_labels:
            if candidate in distribution:
                return distribution[candidate]
        return None

    @staticmethod
    def _extract_series_values(series_data: list[Any]) -> list[Any] | None:
        """兼容纯数值数组和对象点结构，统一抽取用于校验的数值。"""
        values: list[Any] = []
        for item in series_data:
            if isinstance(item, dict):
                if "y" in item:
                    values.append(item["y"])
                    continue
                if "y_axis" in item:
                    values.append(item["y_axis"])
                    continue
                if "value" in item:
                    values.append(item["value"])
                    continue
                return None
            else:
                values.append(item)
        return values

    @staticmethod
    def _numeric_sequence_matches(actual_values: list[Any], expected_values: list[Any]) -> bool:
        """比较两组数值序列，允许轻微浮点误差。"""
        if len(actual_values) != len(expected_values):
            return False
        return all(
            VisualAgent._numeric_matches(actual, expected)
            for actual, expected in zip(actual_values, expected_values, strict=False)
        )

    @staticmethod
    def _numeric_matches(actual: Any, expected: Any) -> bool:
        """比较两个数值，允许轻微浮点误差。"""
        try:
            return abs(float(actual) - float(expected)) <= 1e-4
        except (TypeError, ValueError):
            return actual == expected
