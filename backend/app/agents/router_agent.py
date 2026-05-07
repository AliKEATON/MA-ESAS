"""路由 Agent：根据用户问题决定后续启用哪些分析能力。"""

from __future__ import annotations

from app.agents.llm import LLMUnavailableError, invoke_structured_output
from app.schemas.agent_protocol import ResponseStyle, RouteDecision
from app.utils.logger import logger


class RouterAgent:
    """商品分析路由 Agent，负责输出统一的路由决策。"""

    # 路由提示词只负责“是否启用各个 Agent”的判定，不再负责细粒度统计目标选择。
    SYSTEM_PROMPT = """
你是商品分析多 Agent 系统中的 router_agent，也是整个工作流的任务路由核心。

你的唯一职责：
1. 判断用户问题是否属于商品分析。
2. 判断后续是否需要启动 sql_agent。
3. 判断后续是否需要启动 rag_agent。
4. 判断后续是否需要启动 visual_agent。

你必须严格遵守以下规则：
- 你的输出必须是严格 JSON，并且完全符合 RouteDecision 结构。
- 你不能输出 markdown，不能输出额外解释，不能输出代码块。
- 如果 has_product=false，则不要分配任何依赖商品数据的分析任务：
  - need_sql=false；
  - need_rag=false；
  - need_visual=false；
- 当用户明确要求“可视化 / 图 / 图表 / 分布图 / 趋势图 / 柱状图 / 饼图”等表达时，need_visual=true。
- router_agent 只决定是否需要可视化，不决定具体画哪种图；具体图表决策交给 visual_agent。
- 若用户问题涉及“原因 / 为什么 / 评论里怎么说 / 用户反馈 / 吐槽 / 优缺点 / 体验问题”等，需要评论语义支撑时，need_rag=true。
- 若问题涉及评分、差评率、数量、占比、分布、维度统计、趋势等结构化指标时，need_sql=true。
- response_style 一般取：
  - professional_analysis：商品分析主路径
  - brief_answer：澄清场景
- reason 必须是一句简洁中文，说明为什么这样路由。

路由原则：
- “分析商品评分情况” -> 通常 need_sql=true，need_visual 视是否明确要求图表。
- “分析商品评分并可视化” -> need_sql=true, need_visual=true。
- “商品差评率是多少” -> need_sql=true, need_visual=false。
- “商品差评分布并给出原因” -> need_sql=true, need_visual=true, need_rag=true。
- “大家都在吐槽什么” -> 通常 need_rag=true，若涉及占比或分布可同时 need_sql=true。
"""

    @classmethod
    def route(cls, question: str, has_product: bool = True) -> RouteDecision:
        """调用大模型生成当前问题的结构化路由决策。"""
        # 仅暴露允许的分析与可视化目标，避免模型返回协议外字段。
        payload = {
            "question": question,
            "has_product": has_product,
        }
        try:
            return invoke_structured_output(
                system_prompt=cls.SYSTEM_PROMPT,
                payload=payload,
                schema=RouteDecision,
                temperature=0.1,
            )
        except LLMUnavailableError as exc:
            logger.warning("RouterAgent falling back to rule-based routing: {}", exc)
        except Exception as exc:
            logger.exception("RouterAgent structured generation failed, fallback enabled: {}", exc)
        return cls._rule_based_route(question=question, has_product=has_product)

    @classmethod
    def _rule_based_route(cls, question: str, has_product: bool) -> RouteDecision:
        """在大模型不可用时，使用保守规则生成兜底路由。"""
        normalized = question.strip().lower()
        need_visual = has_product and cls._detect_need_visual(question, normalized)
        need_rag = has_product and cls._detect_need_rag(question, normalized)
        need_sql = has_product and cls._detect_need_sql(question, normalized)

        if not has_product:
            return RouteDecision(
                need_sql=False,
                need_rag=False,
                need_visual=False,
                response_style=ResponseStyle.BRIEF_ANSWER,
                reason="当前未绑定商品，依赖商品数据的分析能力不会启动，将由 answer_agent 直接回答。",
            )

        return RouteDecision(
            need_sql=need_sql,
            need_rag=need_rag,
            need_visual=need_visual,
            response_style=ResponseStyle.PROFESSIONAL_ANALYSIS,
            reason=cls._build_reason(need_sql, need_rag, need_visual),
        )

    @staticmethod
    def _detect_need_visual(question: str, normalized_question: str) -> bool:
        """判断用户是否明确需要图表或可视化表达。"""
        return any(
            keyword in question or keyword in normalized_question
            for keyword in ("可视化", "图", "图表", "分布", "趋势", "占比", "柱状图", "折线图", "饼图")
        )

    @staticmethod
    def _detect_need_rag(question: str, normalized_question: str) -> bool:
        """判断用户是否需要评论语义证据支撑。"""
        return any(
            keyword in question or keyword in normalized_question
            for keyword in ("原因", "为什么", "评价", "评论", "吐槽", "体验", "问题", "差评", "优点", "缺点")
        )

    @staticmethod
    def _detect_need_sql(question: str, normalized_question: str) -> bool:
        """判断用户是否需要结构化统计分析能力。"""
        sql_hints = ("评分", "差评", "均分", "占比", "数量", "分布", "统计", "rate", "score")
        return any(keyword in question or keyword in normalized_question for keyword in sql_hints)

    @staticmethod
    def _build_reason(need_sql: bool, need_rag: bool, need_visual: bool) -> str:
        """构造兜底路由说明文本。"""
        capabilities = []
        if need_sql:
            capabilities.append("统计分析")
        if need_rag:
            capabilities.append("评论语义分析")
        if need_visual:
            capabilities.append("可视化生成")
        capability_text = "、".join(capabilities) or "基础澄清"
        return f"问题将使用{capability_text}能力。"
