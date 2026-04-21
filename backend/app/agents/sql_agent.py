"""统计分析 Agent：基于受控工具规划与结构化统计结果输出。"""

from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd
from sqlalchemy.orm import Session

from app.agents.llm import LLMUnavailableError, invoke_structured_output
from app.models import Comment
from app.schemas.agent_protocol import SQLAgentResult, SQLToolCall, SQLToolPlan
from app.utils.logger import logger


class SQLAgent:
    """商品统计分析 Agent，负责规划统计工具并生成标准统计结果。"""

    # analysis_target 到受控统计工具名的固定映射，避免开放任意 SQL。
    TOOL_REGISTRY = {
        "score_summary": "get_score_summary",
        "score_distribution": "get_score_distribution",
        "bad_review_rate": "get_bad_review_rate",
        "bad_review_distribution": "get_bad_review_distribution",
        "dimension_stats": "get_dimension_stats",
    }
    TOOL_TO_TARGET = {tool: target for target, tool in TOOL_REGISTRY.items()}

    PLAN_PROMPT = """
你是 sql_agent，是商品分析系统中的统计分析专家。

你的职责不是自由生成 SQL，而是根据用户问题与路由目标，选择“受控统计工具”。
你只能做两件事：
1. 判断本轮统计分析需要调用哪些工具；
2. 以严格结构化的方式输出工具调用计划。

必须严格遵守：
- 只允许从以下工具中选择：
  - get_score_summary
  - get_score_distribution
  - get_bad_review_rate
  - get_bad_review_distribution
  - get_dimension_stats
- 绝不允许生成任意 SQL。
- tool_calls 必须与 analysis_targets 对应，不得添加无关工具。
- 若多个 targets 可以由同一工具覆盖，也要保持最小必要调用。
- 输出必须严格符合 SQLToolPlan 结构。
- args 中必须包含 product_id。
- 不要输出 markdown，不要输出额外解释。

工具与目标映射参考：
- score_summary -> get_score_summary
- score_distribution -> get_score_distribution
- bad_review_rate -> get_bad_review_rate
- bad_review_distribution -> get_bad_review_distribution
- dimension_stats -> get_dimension_stats
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
- description 必须紧扣用户问题和 analysis_targets。
- 如果数据为空或评论不足，要明确说明，而不是编造结论。
- 输出必须严格符合 SQLAgentResult 结构。
- 不要输出 markdown，不要输出额外解释。
"""

    @staticmethod
    def run(
        db: Session,
        product_id: int,
        question: str = "",
        analysis_targets: list[str] | None = None,
    ) -> SQLAgentResult:
        """执行统计分析主流程并返回草案协议要求的结构化结果。"""
        analysis_targets = SQLAgent._normalize_analysis_targets(analysis_targets) # 1.1筛选分析目标
        tool_calls = SQLAgent._plan_tool_calls(
            product_id=product_id,
            question=question,
            analysis_targets=analysis_targets,
        ) # 1.2返回调用工具计划列表（llm）
        metrics = SQLAgent._execute_tool_calls(
            db=db,
            product_id=product_id,
            tool_calls=tool_calls,
        ) # 1.3调用工具返回指标
        payload = {
            "question": question,
            "analysis_targets": analysis_targets,
            "tool_calls": [call.model_dump() for call in tool_calls],
            "actual_metrics": metrics,
        }
        try:
            return invoke_structured_output(
                system_prompt=SQLAgent.SUMMARIZE_PROMPT,
                payload=payload,
                schema=SQLAgentResult,
                temperature=0.1,
            ) # 2.返回结构化输出（llm）
        except LLMUnavailableError as exc:
            logger.warning("SQLAgent summarizer falling back to local description: {}", exc)
        except Exception as exc:
            logger.exception("SQLAgent structured summarization failed, fallback enabled: {}", exc)
        return SQLAgentResult(
            tool_calls=tool_calls,
            metrics=metrics,
            description=SQLAgent._build_description(metrics, analysis_targets),
        )

    @staticmethod
    def _plan_tool_calls(product_id: int, question: str, analysis_targets: list[str]) -> list[SQLToolCall]:
        """先由大模型规划受控工具调用，再在失败时回退到确定性映射。"""
        if not analysis_targets:
            return []

        payload = {
            "question": question,
            "product_id": product_id,
            "analysis_targets": analysis_targets,
            "allowed_tools": list(SQLAgent.TOOL_REGISTRY.values()),
        }
        try:
            plan = invoke_structured_output(
                system_prompt=SQLAgent.PLAN_PROMPT,
                payload=payload,
                schema=SQLToolPlan,
                temperature=0.0,
            )
            sanitized_calls = SQLAgent._sanitize_tool_calls(
                product_id=product_id,
                analysis_targets=analysis_targets,
                tool_calls=plan.tool_calls,
            )
            return sanitized_calls or SQLAgent._build_tool_calls(product_id, analysis_targets)
        except LLMUnavailableError as exc:
            logger.warning("SQLAgent tool planner falling back to deterministic mapping: {}", exc)
        except Exception as exc:
            logger.exception("SQLAgent tool planning failed, fallback enabled: {}", exc)
        return SQLAgent._build_tool_calls(product_id, analysis_targets)

    @staticmethod
    def _normalize_analysis_targets(analysis_targets: list[str] | None) -> list[str]:
        """清洗并去重分析目标，只保留协议允许的 target。"""
        if not analysis_targets:
            return []

        normalized_targets: list[str] = []
        for target in analysis_targets:
            cleaned_target = str(target).strip()
            if cleaned_target in SQLAgent.TOOL_REGISTRY and cleaned_target not in normalized_targets:
                normalized_targets.append(cleaned_target)
        return normalized_targets

    @staticmethod
    def _sanitize_tool_calls(
        product_id: int,
        analysis_targets: list[str],
        tool_calls: list[SQLToolCall],
    ) -> list[SQLToolCall]:
        """对白名单、目标一致性和参数进行硬校验，避免模型越权规划。"""
        allowed_tools = {
            SQLAgent.TOOL_REGISTRY[target]
            for target in analysis_targets
            if target in SQLAgent.TOOL_REGISTRY
        }
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
    def _load_comments_df(db: Session, product_id: int) -> pd.DataFrame:
        """载入指定商品评论为 DataFrame，供受控统计工具执行。"""
        comments = db.query(Comment).filter(Comment.product_id == product_id).all()
        if not comments:
            return pd.DataFrame(columns=["score", "dimension", "dimension_score"])

        return pd.DataFrame([
            {
                "score": item.score,
                "dimension": item.dimension or "未分类",
                "dimension_score": item.dimension_score if item.dimension_score is not None else item.score,
            }
            for item in comments
        ])

    @staticmethod
    def _execute_tool_calls(
        db: Session,
        product_id: int,
        tool_calls: list[SQLToolCall],
    ) -> dict[str, Any]:
        """按受控工具计划执行真实统计工具，并聚合最终 metrics。"""
        if not tool_calls:
            return {}

        comments_df = SQLAgent._load_comments_df(db=db, product_id=product_id)
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
            return SQLAgent._get_score_summary(conn)
        if tool_name == "get_score_distribution":
            return SQLAgent._get_score_distribution(conn)
        if tool_name == "get_bad_review_rate":
            return SQLAgent._get_bad_review_rate(conn)
        if tool_name == "get_bad_review_distribution":
            return SQLAgent._get_bad_review_distribution(conn)
        if tool_name == "get_dimension_stats":
            return SQLAgent._get_dimension_stats(conn)
        raise ValueError(f"Unsupported SQL tool: {tool_name}")

    @staticmethod
    def _get_score_summary(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                ROUND(AVG(score), 2) AS avg_score,
                SUM(CASE WHEN score <= 2 THEN 1 ELSE 0 END) AS low_score_count
            FROM comments_df
            """
        ).fetchone()
        return {
            "score_summary": {
                "total_count": int(row[0] or 0),
                "avg_score": float(row[1] or 0),
                "low_score_count": int(row[2] or 0),
            }
        }

    @staticmethod
    def _get_score_distribution(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT score, COUNT(*) AS count
            FROM comments_df
            GROUP BY score
            ORDER BY score
            """
        ).fetchall()
        distribution = {score: 0 for score in range(1, 6)}
        for score, count in rows:
            distribution[int(score)] = int(count)
        return {"score_distribution": distribution}

    @staticmethod
    def _get_bad_review_rate(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT ROUND(AVG(CASE WHEN score <= 2 THEN 1.0 ELSE 0.0 END), 4) AS bad_review_rate
            FROM comments_df
            """
        ).fetchone()
        return {"bad_review_rate": float(row[0] or 0)}

    @staticmethod
    def _get_dimension_stats(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT
                dimension,
                COUNT(*) AS comment_count,
                ROUND(AVG(score), 2) AS avg_score,
                ROUND(AVG(CASE WHEN score <= 2 THEN 1.0 ELSE 0.0 END), 4) AS bad_review_rate,
                SUM(CASE WHEN score <= 2 THEN 1 ELSE 0 END) AS bad_review_count
            FROM comments_df
            GROUP BY dimension
            ORDER BY comment_count DESC, dimension ASC
            """
        ).fetchall()
        return {
            "dimension_stats": {
                str(dimension): {
                    "comment_count": int(comment_count),
                    "avg_score": float(avg_score or 0),
                    "bad_review_rate": float(bad_review_rate or 0),
                    "bad_review_count": int(bad_review_count or 0),
                }
                for dimension, comment_count, avg_score, bad_review_rate, bad_review_count in rows
            }
        }

    @staticmethod
    def _get_bad_review_distribution(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
        dimension_stats = SQLAgent._get_dimension_stats(conn).get("dimension_stats", {})
        return {
            "bad_review_distribution": {
                dimension: values["bad_review_count"]
                for dimension, values in dimension_stats.items()
                if values["bad_review_count"] > 0
            }
        }

    @staticmethod
    def _build_tool_calls(product_id: int, analysis_targets: list[str]) -> list[SQLToolCall]:
        """根据分析目标构造确定性的受控工具调用列表。"""
        tool_calls: list[SQLToolCall] = []
        if "score_summary" in analysis_targets:
            tool_calls.append(SQLToolCall(tool="get_score_summary", args={"product_id": product_id}))
        if "score_distribution" in analysis_targets:
            tool_calls.append(SQLToolCall(tool="get_score_distribution", args={"product_id": product_id}))
        if "bad_review_rate" in analysis_targets:
            tool_calls.append(SQLToolCall(tool="get_bad_review_rate", args={"product_id": product_id}))
        if "bad_review_distribution" in analysis_targets:
            tool_calls.append(SQLToolCall(tool="get_bad_review_distribution", args={"product_id": product_id}))
        if "dimension_stats" in analysis_targets:
            tool_calls.append(SQLToolCall(tool="get_dimension_stats", args={"product_id": product_id}))
        return tool_calls

    @staticmethod
    def _build_description(metrics: dict[str, Any], analysis_targets: list[str]) -> str:
        """在大模型不可用时，根据统计结果生成兜底中文摘要。"""
        if not analysis_targets:
            return "当前未指定统计分析目标，sql_agent 未执行统计工具。"

        score_summary = metrics.get("score_summary") or {}
        total_count = int(score_summary.get("total_count", 0) or 0)
        avg_score = float(score_summary.get("avg_score", 0) or 0)
        bad_review_rate = float(metrics.get("bad_review_rate", 0) or 0)

        if "score_summary" in analysis_targets and total_count <= 0:
            return "当前没有可用评论，无法进行统计分析。"

        parts: list[str] = []
        if "score_summary" in analysis_targets:
            parts.append(f"共统计 {total_count} 条评论，平均评分 {avg_score:.2f}。")
        elif not metrics:
            return "当前没有产出可用的统计结果。"

        if "bad_review_rate" in analysis_targets or "bad_review_distribution" in analysis_targets:
            parts.append(f"差评率约为 {bad_review_rate * 100:.1f}%。")
        if "bad_review_distribution" in analysis_targets:
            bad_distribution = metrics.get("bad_review_distribution") or {}
            if bad_distribution:
                top_dimension = max(bad_distribution.items(), key=lambda item: item[1])[0]
                parts.append(f"差评主要集中在 {top_dimension} 维度。")
        elif "dimension_stats" in analysis_targets:
            dimension_stats = metrics.get("dimension_stats") or {}
            if dimension_stats:
                top_dimension = max(dimension_stats.items(), key=lambda item: item[1].get("comment_count", 0))[0]
                parts.append(f"当前评论最集中的维度为 {top_dimension}。")
        return "".join(parts) or "统计工具已执行，但当前没有可总结的关键结果。"
