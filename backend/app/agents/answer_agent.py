"""回答整合 Agent：汇总多路分析结果并生成候选答复。"""

from __future__ import annotations

from app.agents.llm import LLMUnavailableError, invoke_structured_output
from app.schemas.agent_protocol import AnswerDraft, RAGAgentResult, RouteDecision, SQLAgentResult, VisualAgentResult
from app.utils.logger import logger


class AnswerAgent:
    """负责把 SQL、RAG、可视化结果整合成面向用户的回答草稿。"""

    SYSTEM_PROMPT = """
你是 answer_agent，负责把多 Agent 分析结果整合成可以直接展示给用户的候选回答。

输入中可能包含：
- question：用户原始问题
- route_decision：路由阶段给出的回答风格与任务意图
- sql_result：统计分析结果
- rag_result：评论证据与语义洞察
- visual_result：已经生成的图表结果

你的核心目标：
1. 直接回答 question，而不是复述分析过程。
2. 优先整合最有信息价值、最能支撑结论的结果。
3. 让 answer 与 answer_points 彼此一致，便于下游 master_agent 审查。
4. 严格输出 AnswerDraft 结构，不要输出额外内容。

回答组织要求：
- 如果有 sql_result，优先给出明确统计结论。
- 如果有 rag_result，补充“为什么会这样”的语义原因或评论证据总结。
- 如果有 visual_result，可以自然提及“已生成某图表，可结合查看”，但不要编造图表细节。
- 如果某类结果缺失，只基于已有结果保守作答，不要虚构补充。

风格要求：
- response_style=brief_answer：直接给结论，尽量短，避免铺垫。
- response_style=professional_analysis：简洁但有分析感，优先“结论 + 原因”结构。
- response_style=report_style：表达可更正式，但仍然直接回答问题，不要写成 markdown 报告。

answer 要求：
- 必须使用中文。
- 必须直接回应 question。
- 不能只说“已分析”“请查看图表”这类空话。
- 不能编造统计值、证据、维度、图表内容。

answer_points 要求：
- 输出 2-5 条关键结论；如果有效结论不足，可以少于 2 条，但不能编造。
- 每条都应是可核对的短结论，不要写成长段落。
- 尽量覆盖：统计结论、主要原因、图表可视化结论（如适用）。
- 不要输出“好的”“已回答”“请查看结果”这类无信息内容。

请记住：
- answer 是给用户看的最终话术。
- answer_points 是给审查链路看的关键结论摘要。
- 两者必须语义一致，不能互相矛盾。
"""

    @staticmethod
    def run(
        question: str,
        route_decision: RouteDecision,
        sql_result: SQLAgentResult | None = None,
        rag_result: RAGAgentResult | None = None,
        visual_result: VisualAgentResult | None = None,
    ) -> AnswerDraft:
        """调用大模型生成回答草稿，失败时回退到本地保守整合逻辑。"""
        payload = {
            "question": question,
            "route_decision": route_decision.model_dump(),
            "sql_result": sql_result.model_dump() if sql_result is not None else None,
            "rag_result": rag_result.model_dump() if rag_result is not None else None,
            "visual_result": visual_result.model_dump() if visual_result is not None else None,
        }
        try:
            return invoke_structured_output(
                system_prompt=AnswerAgent.SYSTEM_PROMPT,
                payload=payload,
                schema=AnswerDraft,
                temperature=0.2,
            )
        except LLMUnavailableError as exc:
            logger.warning("AnswerAgent 回退到规则草稿生成: {}", exc)
        except Exception as exc:
            logger.exception("AnswerAgent 结构化生成失败，启用 fallback: {}", exc)
        return AnswerAgent._fallback_run(
            question=question,
            route_decision=route_decision,
            sql_result=sql_result,
            rag_result=rag_result,
            visual_result=visual_result,
        )

    @staticmethod
    def _fallback_run(
        question: str,
        route_decision: RouteDecision,
        sql_result: SQLAgentResult | None = None,
        rag_result: RAGAgentResult | None = None,
        visual_result: VisualAgentResult | None = None,
    ) -> AnswerDraft:
        """在大模型不可用时，围绕原始问题生成可交付的保守答复。"""
        points = AnswerAgent._build_answer_points(
            sql_result=sql_result,
            rag_result=rag_result,
            visual_result=visual_result,
        )
        if not points:
            points = [f"针对“{question}”，当前未产出足够的分析结果，建议稍后重试或补充更明确的问题信息。"]
        answer = AnswerAgent._compose_answer_text(
            question=question,
            response_style=route_decision.response_style.value,
            points=points,
        )
        return AnswerDraft(answer=answer, answer_points=points[:5])

    @staticmethod
    def _build_answer_points(
        sql_result: SQLAgentResult | None = None,
        rag_result: RAGAgentResult | None = None,
        visual_result: VisualAgentResult | None = None,
    ) -> list[str]:
        """从各子 Agent 结果中提取可核对的关键结论点。"""
        raw_points: list[str] = []
        if sql_result is not None and sql_result.description:
            raw_points.append(sql_result.description.strip())
        if rag_result is not None:
            if rag_result.insight_points:
                raw_points.extend(point.strip() for point in rag_result.insight_points if point and point.strip())
            elif rag_result.insight:
                raw_points.append(rag_result.insight.strip())
        if visual_result is not None and visual_result.charts:
            chart_titles = [chart.title.strip() for chart in visual_result.charts if chart.title and chart.title.strip()]
            if chart_titles:
                visible_titles = "、".join(dict.fromkeys(chart_titles[:3]))
                raw_points.append(f"已生成{len(visual_result.charts)}个图表，包括{visible_titles}，可结合图表进一步查看。")
            else:
                raw_points.append(f"已生成{len(visual_result.charts)}个可视化图表，可结合图表进一步查看。")

        # answer_points 面向后续审查和展示，保持短句、去重、最多 5 条。
        normalized_points: list[str] = []
        seen: set[str] = set()
        for point in raw_points:
            compact_point = " ".join(point.split())
            if not compact_point or compact_point in seen:
                continue
            normalized_points.append(compact_point)
            seen.add(compact_point)
            if len(normalized_points) >= 5:
                break
        return normalized_points

    @staticmethod
    def _compose_answer_text(question: str, response_style: str, points: list[str]) -> str:
        """根据路由阶段给出的回答风格，组织最终答复文本。"""
        if response_style == "brief_answer":
            return "；".join(points[:2])
        if response_style == "report_style":
            return f"针对“{question}”，结论如下：{' '.join(points)}"
        return f"针对“{question}”，结合当前分析结果，{' '.join(points)}"
