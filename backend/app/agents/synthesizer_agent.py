"""Structured summary synthesizer for analysis results."""

from __future__ import annotations

from typing import Any

from app.models import Product
from app.utils.logger import logger


class SynthesizerAgent:
    """负责把路由、统计和证据整合成面向用户的结构化结论。"""

    MODE_LABELS = {
        "negative_review": "差评分析",
        "comparison": "对比分析",
        "value_assessment": "值不值得买评估",
        "general_review": "综合评价",
    }

    @classmethod
    def build_summary(
        cls,
        question: str,
        product: Product,
        route_plan: dict[str, Any],
        stats: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> str:
        """生成结构化摘要，突出问题焦点、核心发现和证据支撑。"""
        focus_dimensions = route_plan.get("focus_dimensions") or ["综合"]
        focus_text = "、".join(str(item) for item in focus_dimensions)
        mode_label = cls.MODE_LABELS.get(route_plan.get("analysis_mode"), "综合评价")

        total_count = int(stats.get("total_count", 0) or 0)
        avg_score = float(stats.get("avg_score", 0) or 0)
        bad_rate = float(stats.get("bad_rate", 0) or 0)

        if total_count <= 0:
            summary = (
                f"问题：{question.strip()}\n"
                f"结论：商品 {product.external_product_id} 当前缺少可分析评论，无法输出可靠结论。\n"
                f"重点维度：{focus_text}\n"
                "建议：请先补充抓取数据后再发起分析。"
            )
            logger.info(
                "Synthesizer generated empty-data summary: product_id={} focus_dimensions={}",
                product.id,
                focus_dimensions,
            )
            return summary

        overview = (
            f"问题：{question.strip()}\n"
            f"结论：本次属于{mode_label}，共分析 {total_count} 条评论，平均评分 {avg_score:.2f}，"
            f"差评率 {cls._format_percentage(bad_rate)}。"
        )
        focus_line = f"重点维度：{focus_text}。{cls._build_focus_insight(stats, focus_dimensions)}"
        evidence_line = f"证据摘要：{cls._build_evidence_brief(evidence)}"
        return "\n".join([overview, focus_line, evidence_line])

    @staticmethod
    def _build_focus_insight(stats: dict[str, Any], focus_dimensions: list[str]) -> str:
        """生成重点维度的统计发现，没有命中时回退到整体维度概览。"""
        dimension_stats = stats.get("dimension_stats", {}) or {}
        focus_dimension_stats = stats.get("focus_dimension_stats", {}) or {}

        insight_items: list[str] = []
        for dimension in focus_dimensions:
            detail = focus_dimension_stats.get(dimension) or dimension_stats.get(dimension)
            if not detail:
                continue
            insight_items.append(
                f"{dimension}相关评论 {detail.get('comment_count', 0)} 条，"
                f"均分 {float(detail.get('avg_score', 0) or 0):.2f}，"
                f"差评率 {SynthesizerAgent._format_percentage(detail.get('bad_rate', 0) or 0)}"
            )

        if insight_items:
            return "核心发现：" + "；".join(insight_items) + "。"

        if not dimension_stats:
            return "核心发现：当前没有可用的维度统计。"

        top_dimension, top_detail = max(
            dimension_stats.items(),
            key=lambda item: item[1].get("comment_count", 0),
        )
        return (
            "核心发现：当前最活跃的评价维度是"
            f"{top_dimension}，共有 {top_detail.get('comment_count', 0)} 条评论，"
            f"均分 {float(top_detail.get('avg_score', 0) or 0):.2f}。"
        )

    @staticmethod
    def _build_evidence_brief(evidence: list[dict[str, Any]]) -> str:
        """将检索到的证据压缩成适合摘要展示的短句。"""
        if not evidence:
            return "暂未检索到高相关证据。"

        snippets: list[str] = []
        for item in evidence[:2]:
            content = str(item.get("content", "")).strip()
            compact = " ".join(content.split())
            if len(compact) > 28:
                compact = compact[:28] + "..."
            dimension = item.get("dimension") or "未分类"
            similarity = float(item.get("similarity", 0) or 0)
            snippets.append(f"{dimension}({similarity:.2f})：{compact}")
        return "；".join(snippets) + "。"

    @staticmethod
    def _format_percentage(value: float) -> str:
        """把 0 到 1 之间的比例格式化为百分比字符串。"""
        return f"{float(value) * 100:.1f}%"
