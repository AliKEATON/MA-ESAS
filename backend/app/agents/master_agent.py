"""???? Agent????????????????"""

from __future__ import annotations

import re

from app.agents.llm import LLMUnavailableError, invoke_structured_output
from app.schemas.agent_protocol import MasterDecision, MasterDecisionType, RetryFromAgent, RouteDecision, VisualAgentResult
from app.utils.logger import logger


class MasterAgent:
    """???????????????????????"""

    _QUESTION_STOPWORDS = {
        "?",
        "??",
        "??",
        "??",
        "??",
        "??",
        "??",
        "??",
        "??",
        "???",
        "??",
        "??",
        "???",
        "??",
        "??",
        "??",
        "??",
    }

    SYSTEM_PROMPT = """
你是 master_agent，负责对多 Agent 链路产出的候选结果做最终质量审查。

输入中可能包含：
- question：用户原始问题
- route_decision：路由阶段给出的任务意图与回答风格
- answer_text：answer_agent 生成的候选回答
- answer_points：answer_agent 提炼的关键结论点
- visual_result：已经生成的图表结果
- retry_count / max_retry：当前重试次数与上限

你的核心目标：
1. 判断 answer_text 是否真正回答了 question。
2. 判断 answer_points 是否提供了足够的关键结论，而不是空泛短句。
3. 在用户需要可视化时，判断 visual_result 是否足够支撑交付。
4. 如果当前结果不完整，明确指出缺失项，并给出最合适的 retry_from。

审查优先级：
1. 先看是否答题：answer_text 是否直接回应 question。
2. 再看是否有结论：answer_points 是否提炼出关键事实或关键判断。
3. 最后看图表是否满足需求：如果用户明确需要图表，visual_result 不能为空。

决策规则：
- 如果 answer_text 已直接回答问题，answer_points 有效，且所需图表齐备，则 decision=pass。
- 如果主要问题是缺图表，优先 decision=retry，retry_from=visual_agent。
- 如果主要问题是 answer_text 没答题、答非所问，或 answer_points 过弱，优先 decision=retry，retry_from=answer_agent。
- 如果已经达到最大重试次数，不要继续要求重试，应输出 fallback_pass 或 fail。

missing_items 填写要求：
- 只列真正缺失或明显不足的项。
- 可使用的典型值包括：answer、answer_points、visual_result。

reason 填写要求：
- 使用简洁中文。
- 直接说明为什么 pass 或 retry。
- 不要复述整段输入，不要输出 markdown。

输出要求：
- 只能输出 MasterDecision 结构。
- 不要输出任何额外解释。
"""

    @staticmethod
    def run(
        question: str,
        route_decision: RouteDecision,
        answer_text: str,
        answer_points: list[str] | None = None,
        visual_result: VisualAgentResult | None = None,
        retry_count: int = 0,
        max_retry: int = 1,
    ) -> MasterDecision:
        """????????????????????????"""
        payload = {
            "question": question,
            "route_decision": route_decision.model_dump(),
            "answer_text": answer_text,
            "answer_points": answer_points or [],
            "visual_result": visual_result.model_dump() if visual_result is not None else None,
            "retry_count": retry_count,
            "max_retry": max_retry,
        }
        try:
            return invoke_structured_output(
                system_prompt=MasterAgent.SYSTEM_PROMPT,
                payload=payload,
                schema=MasterDecision,
                temperature=0.1,
            )
        except LLMUnavailableError as exc:
            logger.warning("MasterAgent ???????: {}", exc)
        except Exception as exc:
            logger.exception("MasterAgent ?????????? fallback: {}", exc)
        return MasterAgent._fallback_run(
            question=question,
            route_decision=route_decision,
            answer_text=answer_text,
            answer_points=answer_points or [],
            visual_result=visual_result,
            retry_count=retry_count,
            max_retry=max_retry,
        )

    @staticmethod
    def _has_effective_answer_points(answer_points: list[str] | None) -> bool:
        """??????????????????"""
        if not answer_points:
            return False

        weak_markers = {
            "??",
            "???",
            "???",
            "?????",
            "???????",
        }
        effective_count = 0
        for point in answer_points:
            normalized = " ".join(point.split())
            if not normalized:
                continue
            if normalized in weak_markers:
                continue
            if len(normalized) < 4:
                continue
            effective_count += 1
        return effective_count > 0

    @staticmethod
    def _extract_question_keywords(question: str) -> list[str]:
        """???????????? fallback ????????????"""
        candidates = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{3,}", question)
        keywords: list[str] = []
        for candidate in candidates:
            normalized = candidate.strip().lower()
            if not normalized or normalized in MasterAgent._QUESTION_STOPWORDS:
                continue
            keywords.append(normalized)
        return keywords

    @staticmethod
    def _covers_question(question: str, answer_text: str) -> bool:
        """?????????????????????"""
        normalized_answer = answer_text.strip().lower()
        if not normalized_answer:
            return False

        keywords = MasterAgent._extract_question_keywords(question)
        if not keywords:
            return True
        return any(keyword in normalized_answer for keyword in keywords)

    @staticmethod
    def _fallback_run(
        question: str,
        route_decision: RouteDecision,
        answer_text: str,
        answer_points: list[str] | None = None,
        visual_result: VisualAgentResult | None = None,
        retry_count: int = 0,
        max_retry: int = 1,
    ) -> MasterDecision:
        """????????????????????????????"""
        missing_items: list[str] = []
        if route_decision.need_visual and (visual_result is None or not visual_result.charts):
            missing_items.append("visual_result")
        if not answer_text.strip():
            missing_items.append("answer")
        elif not MasterAgent._covers_question(question, answer_text):
            missing_items.append("answer")
        if not MasterAgent._has_effective_answer_points(answer_points):
            missing_items.append("answer_points")
        if not missing_items:
            return MasterDecision(
                decision=MasterDecisionType.PASS,
                reason="??????????????????",
                missing_items=[],
                retry_from=None,
            )
        if retry_count < max_retry:
            retry_from = RetryFromAgent.VISUAL_AGENT if "visual_result" in missing_items else RetryFromAgent.ANSWER_AGENT
            return MasterDecision(
                decision=MasterDecisionType.RETRY,
                reason="??????????????????????????",
                missing_items=missing_items,
                retry_from=retry_from,
            )
        return MasterDecision(
            decision=MasterDecisionType.FALLBACK_PASS,
            reason="???????????????????",
            missing_items=missing_items,
            retry_from=None,
        )
