"""路由 Agent：根据用户问题决定后续启用哪些分析能力。"""

from __future__ import annotations

from app.agents.llm import LLMUnavailableError, invoke_structured_output
from app.schemas.agent_protocol import ResponseStyle, RouteDecision
from app.utils.logger import logger


class RouterAgent:
    """商品分析路由 Agent，负责输出统一的路由决策。"""

    # 路由提示词负责把“用户问题 -> 协议化路由决策”约束在固定字段内。
    SYSTEM_PROMPT = """
你是商品分析多 Agent 系统中的 router_agent，也是整个工作流的任务路由核心。

你的唯一职责：
1. 判断用户问题是否属于商品分析。
2. 判断后续是否需要启动 sql_agent。
3. 判断后续是否需要启动 rag_agent。
4. 判断后续是否需要启动 visual_agent。
5. 产出明确、可执行的 analysis_targets。

你必须严格遵守以下规则：
- 你的输出必须是严格 JSON，并且完全符合 RouteDecision 结构。
- 你不能输出 markdown，不能输出额外解释，不能输出代码块。
- 如果 has_product=false，则不要分配任何依赖商品数据的分析任务：
  - need_sql=false；
  - need_rag=false；
  - need_visual=false；
  - analysis_targets=[]。
- analysis_targets 必须优先从以下候选中选择，且只保留真正必要的项：
  - score_summary
  - score_distribution
  - bad_review_rate
  - bad_review_distribution
  - dimension_stats
- 当用户明确要求“可视化 / 图 / 图表 / 分布图 / 趋势图 / 柱状图 / 饼图”等表达时，need_visual=true。
- router_agent 只决定是否需要可视化，不决定具体画哪种图，也不输出图表目标；具体图表决策交给 visual_agent。
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
        analysis_targets = cls._build_analysis_targets(question, normalized)
        need_visual = has_product and cls._detect_need_visual(question, normalized)
        need_rag = has_product and cls._detect_need_rag(question, normalized)
        need_sql = has_product and cls._detect_need_sql(question, normalized, analysis_targets)

        if not has_product:
            return RouteDecision(
                need_sql=False,
                need_rag=False,
                need_visual=False,
                analysis_targets=[],
                response_style=ResponseStyle.BRIEF_ANSWER,
                reason="当前未绑定商品，依赖商品数据的分析能力不会启动，将由 answer_agent 直接回答。",
            )

        return RouteDecision(
            need_sql=need_sql,
            need_rag=need_rag,
            need_visual=need_visual,
            analysis_targets=analysis_targets,
            response_style=ResponseStyle.PROFESSIONAL_ANALYSIS,
            reason=cls._build_reason(need_sql, need_rag, need_visual, analysis_targets),
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
    def _detect_need_sql(question: str, normalized_question: str, analysis_targets: list[str]) -> bool:
        """判断用户是否需要结构化统计分析能力。"""
        if analysis_targets:
            return True
        sql_hints = ("评分", "差评", "均分", "占比", "数量", "分布", "统计", "rate", "score")
        return any(keyword in question or keyword in normalized_question for keyword in sql_hints)

    @classmethod
    def _build_analysis_targets(cls, question: str, normalized_question: str) -> list[str]:
        """根据问题语义构造兜底的分析目标列表。"""
        targets: list[str] = []
        if "评分" in question or "score" in normalized_question or "rating" in normalized_question:
            if any(keyword in question for keyword in ("分布", "可视化", "图", "图表")):
                targets.append("score_distribution")
            targets.append("score_summary")
        if "差评率" in question or "bad rate" in normalized_question or "negative review rate" in normalized_question:
            targets.append("bad_review_rate")
        if "差评分布" in question or ("差评" in question and "分布" in question):
            targets.append("bad_review_distribution")
        if any(keyword in question for keyword in ("维度", "物流", "质量", "价格", "售后", "性能")):
            targets.append("dimension_stats")
        return list(dict.fromkeys(targets))

    @staticmethod
    def _build_reason(need_sql: bool, need_rag: bool, need_visual: bool, targets: list[str]) -> str:
        """构造兜底路由说明文本。"""
        capabilities = []
        if need_sql:
            capabilities.append("统计分析")
        if need_rag:
            capabilities.append("评论语义分析")
        if need_visual:
            capabilities.append("可视化生成")
        capability_text = "、".join(capabilities) or "基础澄清"
        return f"问题将使用{capability_text}，分析目标为：{'、'.join(targets) if targets else '无'}。"
