"""统计分析 Agent：基于受控工具规划与结构化统计结果输出。"""

from __future__ import annotations

from typing import Any

import duckdb
from sqlalchemy.orm import Session

from app.agents.llm import LLMUnavailableError, invoke_structured_output
from app.agents.sql_tools import SQLMetricsTools
from app.schemas.agent_protocol import SQLAgentResult, SQLToolCall, SQLToolPlan
from app.utils.logger import logger


class SQLAgent:
    """商品统计分析 Agent，负责规划统计工具并生成标准统计结果。"""

    # 受控统计工具白名单，避免开放任意 SQL。
    TOOL_REGISTRY = {
        "score_summary": "get_score_summary",
        "score_distribution": "get_score_distribution",
        "bad_review_rate": "get_bad_review_rate",
        "positive_review_rate": "get_positive_review_rate",
        "score_band_distribution": "get_score_band_distribution",
        "bad_review_distribution": "get_bad_review_distribution",
        "dimension_stats": "get_dimension_stats",
        "dimension_rankings": "get_dimension_rankings",
        "monthly_score_trend": "get_monthly_score_trend",
        "dimension_score_distribution": "get_dimension_score_distribution",
        "dimension_coverage": "get_dimension_coverage",
        "comment_length_stats": "get_comment_length_stats",
        "low_score_dimension_pairs": "get_low_score_dimension_pairs",
        "dimension_polarization": "get_dimension_polarization",
    }

    PLAN_PROMPT = """
你是 sql_agent，是商品分析系统中的统计分析专家。

你的职责不是自由生成 SQL，而是根据用户问题，选择“受控统计工具”。
你只能做两件事：
1. 判断本轮统计分析需要调用哪些工具；
2. 以严格结构化的方式输出工具调用计划。

必须严格遵守：
- 只允许从以下工具中选择：
  - get_score_summary
  - get_score_distribution
  - get_bad_review_rate
  - get_positive_review_rate
  - get_score_band_distribution
  - get_bad_review_distribution
  - get_dimension_stats
  - get_dimension_rankings
  - get_monthly_score_trend
  - get_dimension_score_distribution
  - get_dimension_coverage
  - get_comment_length_stats
  - get_low_score_dimension_pairs
  - get_dimension_polarization
- 绝不允许生成任意 SQL。
- tool_calls 必须紧扣用户问题，不得添加无关工具。
- 若多个问题点可以由同一工具覆盖，也要保持最小必要调用。
- 输出必须严格符合 SQLToolPlan 结构。
- args 中必须包含 product_id。
- 不要输出 markdown，不要输出额外解释。

常见工具用途参考：
- get_score_summary：总评论数、平均分、低分评论数
- get_score_distribution：1~5 分评分分布
- get_bad_review_rate：差评率
- get_positive_review_rate：好评率
- get_score_band_distribution：好评/中评/差评分段占比
- get_bad_review_distribution：各维度差评数量分布
- get_dimension_stats：各维度评论数、平均分、差评率、差评数
- get_dimension_rankings：各维度在评论量、平均分、差评率上的排序
- get_monthly_score_trend：按月统计评论量、均分、差评率变化
- get_dimension_score_distribution：各维度内部的评分分布
- get_dimension_coverage：各维度评论覆盖量
- get_comment_length_stats：评论长度与长短评论规模
- get_low_score_dimension_pairs：低分评论最集中的维度
- get_dimension_polarization：各维度是否存在高低分两极分化
"""

    SUMMARIZE_PROMPT = """
你是 sql_agent 的结果整理器，负责把受控统计工具返回的数据整理成标准 SQLAgentResult。

你的职责：
1. 保留已经执行过的 tool_calls；
2. 使用输入中的 actual_metrics 作为 metrics 原样输出；
3. 生成一段简洁中文 description，总结最关键的统计发现。

必须严格遵守：
- 不能改写、杜撰或推断输入中不存在的统计值。
- metrics 只能使用 actual_metrics 提供的数据。
- description 必须紧扣用户问题。
- 如果数据为空或评论不足，要明确说明，而不是编造结论。
- 输出必须严格符合 SQLAgentResult 结构。
- 不要输出 markdown，不要输出额外解释。
"""

    @staticmethod
    def run(
        db: Session,
        product_id: int,
        question: str = "",
    ) -> SQLAgentResult:
        """执行统计分析主流程并返回结构化统计结果。"""
        tool_calls = SQLAgent._plan_tool_calls(
            product_id=product_id,
            question=question,
        ) # 1.1 返回调用工具计划列表（llm）
        if not tool_calls:
            logger.warning("SQLAgent skipped because no controlled tools were planned")
            return SQLAgentResult(tool_calls=[], metrics={}, description="")
        metrics = SQLAgent._execute_tool_calls(
            db=db,
            product_id=product_id,
            tool_calls=tool_calls,
        ) # 1.2 调用工具返回指标
        payload = {
            "question": question,
            "tool_calls": [call.model_dump() for call in tool_calls],
            "actual_metrics": metrics,
        }
        try:
            return invoke_structured_output(
                system_prompt=SQLAgent.SUMMARIZE_PROMPT,
                payload=payload,
                schema=SQLAgentResult,
                temperature=0.1,
            ) # 2. 返回结构化输出（llm）
        except LLMUnavailableError as exc:
            logger.warning("SQLAgent summarizer unavailable, returning empty result: {}", exc)
        except Exception as exc:
            logger.exception("SQLAgent structured summarization failed, returning empty result: {}", exc)
        return SQLAgentResult(tool_calls=[], metrics={}, description="")

    @staticmethod
    def _plan_tool_calls(product_id: int, question: str) -> list[SQLToolCall]:
        """先由大模型规划受控工具调用，失败时直接返回空计划。"""
        payload = {
            "question": question,
            "product_id": product_id,
            "allowed_tools": list(SQLAgent.TOOL_REGISTRY.values()),
        }
        try:
            plan = invoke_structured_output(
                system_prompt=SQLAgent.PLAN_PROMPT,
                payload=payload,
                schema=SQLToolPlan,
                temperature=0.0,
            )
            return SQLAgent._sanitize_tool_calls(product_id=product_id, tool_calls=plan.tool_calls)
        except LLMUnavailableError as exc:
            logger.warning("SQLAgent tool planner unavailable, returning empty plan: {}", exc)
        except Exception as exc:
            logger.exception("SQLAgent tool planning failed, returning empty plan: {}", exc)
        return []

    @staticmethod
    def _sanitize_tool_calls(
        product_id: int,
        tool_calls: list[SQLToolCall],
    ) -> list[SQLToolCall]:
        """对白名单和参数进行硬校验，避免模型越权规划。"""
        allowed_tools = set(SQLAgent.TOOL_REGISTRY.values())
        sanitized_calls: list[SQLToolCall] = []
        seen_tools: set[str] = set()

        for call in tool_calls:
            tool_name = str(call.tool).strip()
            if tool_name not in allowed_tools or tool_name in seen_tools:
                continue
            seen_tools.add(tool_name)
            sanitized_calls.append(SQLToolCall(tool=tool_name, args={"product_id": product_id}))

        return sanitized_calls

    @staticmethod
    def _execute_tool_calls(
        db: Session,
        product_id: int,
        tool_calls: list[SQLToolCall],
    ) -> dict[str, Any]:
        """按受控工具计划执行真实统计工具，并聚合最终 metrics。"""
        if not tool_calls:
            return {}

        comments_df = SQLMetricsTools.load_comments_df(db=db, product_id=product_id)
        metrics: dict[str, Any] = {}
        conn = duckdb.connect(":memory:")
        try:
            conn.register("comments_df", comments_df)
            for call in tool_calls:
                metrics.update(SQLAgent._execute_tool(conn=conn, tool_name=call.tool))
            logger.info(
                "SQL agent controlled tool execution finished: product_id={} tool_count={}",
                product_id,
                len(tool_calls),
            )
            return metrics
        finally:
            conn.close()

    @staticmethod
    def _execute_tool(conn: duckdb.DuckDBPyConnection, tool_name: str) -> dict[str, Any]:
        """执行单个受控统计工具并返回对应指标。"""
        if tool_name == "get_score_summary":
            return SQLMetricsTools.get_score_summary(conn)
        if tool_name == "get_score_distribution":
            return SQLMetricsTools.get_score_distribution(conn)
        if tool_name == "get_bad_review_rate":
            return SQLMetricsTools.get_bad_review_rate(conn)
        if tool_name == "get_positive_review_rate":
            return SQLMetricsTools.get_positive_review_rate(conn)
        if tool_name == "get_score_band_distribution":
            return SQLMetricsTools.get_score_band_distribution(conn)
        if tool_name == "get_bad_review_distribution":
            return SQLMetricsTools.get_bad_review_distribution(conn)
        if tool_name == "get_dimension_stats":
            return SQLMetricsTools.get_dimension_stats(conn)
        if tool_name == "get_dimension_rankings":
            return SQLMetricsTools.get_dimension_rankings(conn)
        if tool_name == "get_monthly_score_trend":
            return SQLMetricsTools.get_monthly_score_trend(conn)
        if tool_name == "get_dimension_score_distribution":
            return SQLMetricsTools.get_dimension_score_distribution(conn)
        if tool_name == "get_dimension_coverage":
            return SQLMetricsTools.get_dimension_coverage(conn)
        if tool_name == "get_comment_length_stats":
            return SQLMetricsTools.get_comment_length_stats(conn)
        if tool_name == "get_low_score_dimension_pairs":
            return SQLMetricsTools.get_low_score_dimension_pairs(conn)
        if tool_name == "get_dimension_polarization":
            return SQLMetricsTools.get_dimension_polarization(conn)
        raise ValueError(f"Unsupported SQL tool: {tool_name}")
