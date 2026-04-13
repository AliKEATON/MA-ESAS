from __future__ import annotations

from app.agents.synthesizer_agent import SynthesizerAgent
from app.models import Product


def test_synthesizer_agent_builds_structured_summary() -> None:
    """Synthesizer Agent 应生成包含结论、重点维度和证据摘要的结构化文本。"""
    product = Product(id=1, external_product_id="syn-1001")
    route_plan = {
        "analysis_mode": "negative_review",
        "focus_dimensions": ["物流", "售后"],
    }
    stats = {
        "total_count": 12,
        "avg_score": 2.75,
        "bad_rate": 0.5,
        "dimension_stats": {
            "物流": {"comment_count": 6, "avg_score": 2.0, "bad_rate": 0.6667},
            "售后": {"comment_count": 3, "avg_score": 2.33, "bad_rate": 0.3333},
        },
        "focus_dimension_stats": {
            "物流": {"comment_count": 6, "avg_score": 2.0, "bad_rate": 0.6667},
            "售后": {"comment_count": 3, "avg_score": 2.33, "bad_rate": 0.3333},
        },
    }
    evidence = [
        {"content": "物流太慢了，三天才送到，而且包装破损。", "dimension": "物流", "similarity": 3.2},
        {"content": "售后响应很慢，退款处理拖了很久。", "dimension": "售后", "similarity": 2.8},
    ]

    summary = SynthesizerAgent.build_summary(
        question="请分析这款商品的差评，重点看物流和售后问题。",
        product=product,
        route_plan=route_plan,
        stats=stats,
        evidence=evidence,
    )

    assert "问题：请分析这款商品的差评，重点看物流和售后问题。" in summary
    assert "结论：本次属于差评分析" in summary
    assert "重点维度：物流、售后。" in summary
    assert "物流相关评论 6 条" in summary
    assert "证据摘要：" in summary


def test_synthesizer_agent_handles_empty_comment_stats() -> None:
    """当没有评论数据时，Synthesizer Agent 应返回明确的空数据提示。"""
    product = Product(id=2, external_product_id="syn-1002")
    route_plan = {
        "analysis_mode": "general_review",
        "focus_dimensions": ["综合"],
    }

    summary = SynthesizerAgent.build_summary(
        question="请总结一下这款商品。",
        product=product,
        route_plan=route_plan,
        stats={"total_count": 0, "avg_score": 0, "bad_rate": 0},
        evidence=[],
    )

    assert "当前缺少可分析评论" in summary
    assert "重点维度：综合" in summary
