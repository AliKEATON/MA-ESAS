"""Rule-based router agent for analysis-task planning."""

from __future__ import annotations


class RouterAgent:
    """负责将分析问题路由成后续分析重点。"""

    DIMENSION_KEYWORDS = {
        "物流": ("物流", "配送", "快递", "发货", "到货"),
        "质量": ("质量", "做工", "品控", "耐用", "损坏"),
        "价格": ("价格", "性价比", "值不值", "值得买", "贵不贵"),
        "售后": ("售后", "客服", "退货", "退款", "保修"),
        "性能": ("性能", "速度", "续航", "音质", "体验"),
    }

    @classmethod
    def route_question(cls, question: str) -> dict[str, object]:
        """根据问题文本生成后续分析路由计划。"""
        normalized = question.strip().lower()
        focus_dimensions = cls._extract_focus_dimensions(question)
        analysis_mode = cls._detect_analysis_mode(normalized)
        sql_tasks = cls._build_sql_tasks(analysis_mode, focus_dimensions)
        rag_queries = cls._build_rag_queries(question, focus_dimensions)
        return {
            "analysis_mode": analysis_mode,
            "focus_dimensions": focus_dimensions,
            "sql_tasks": sql_tasks,
            "rag_queries": rag_queries,
            "reason": cls._build_reason(analysis_mode, focus_dimensions),
        }

    @classmethod
    def _detect_analysis_mode(cls, normalized_question: str) -> str:
        """识别当前问题属于哪类分析模式。"""
        if any(keyword in normalized_question for keyword in ("差评", "负面", "问题", "吐槽", "缺点")):
            return "negative_review"
        if any(keyword in normalized_question for keyword in ("对比", "比较", "compare")):
            return "comparison"
        if any(keyword in normalized_question for keyword in ("值得买", "值不值", "推荐", "买吗", "worth")):
            return "value_assessment"
        return "general_review"

    @classmethod
    def _extract_focus_dimensions(cls, question: str) -> list[str]:
        """从问题文本中提取需要重点分析的维度。"""
        focus_dimensions: list[str] = []
        for dimension, keywords in cls.DIMENSION_KEYWORDS.items():
            if any(keyword in question for keyword in keywords):
                focus_dimensions.append(dimension)
        return focus_dimensions or ["综合"]

    @staticmethod
    def _build_sql_tasks(analysis_mode: str, focus_dimensions: list[str]) -> list[str]:
        """构造后续 SQL 聚合阶段需要关注的统计任务。"""
        tasks = ["评分分布", "维度均值", "高频差评统计"]
        if analysis_mode == "comparison":
            tasks.append("维度对比")
        if analysis_mode == "value_assessment":
            tasks.append("性价比评估")
        if focus_dimensions != ["综合"]:
            tasks.append("重点维度聚合")
        return tasks

    @staticmethod
    def _build_rag_queries(question: str, focus_dimensions: list[str]) -> list[str]:
        """构造后续语义检索阶段需要检索的评论查询。"""
        queries = [question.strip()]
        for dimension in focus_dimensions:
            if dimension != "综合":
                queries.append(f"{dimension} 相关用户评价")
        return queries

    @staticmethod
    def _build_reason(analysis_mode: str, focus_dimensions: list[str]) -> str:
        """生成人类可读的路由说明。"""
        return (
            f"问题被识别为 {analysis_mode}，"
            f"后续将重点关注：{'、'.join(focus_dimensions)}。"
        )
