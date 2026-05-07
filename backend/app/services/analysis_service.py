"""Analysis service for task-backed product analysis."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import duckdb
from sqlalchemy.orm import Session

from app.agents.state import AnalysisWorkflowRuntime
from app.agents.sql_tools import SQLMetricsTools
from app.agents.workflow import AnalysisWorkflow
from app.db.database import SessionLocal
from app.models import AnalysisReport, AnalysisTask, Comment, Conversation, Message, Product
from app.models.analysis_task import AnalysisTaskStatus
from app.models.conversation import MessageRole, MessageType
from app.models.product import ProductStatus
from app.schemas.agent_protocol import FinalAnalysisResponse, FinalResponseMeta
from app.services.crawler_service import CrawlerService
from app.services.vector_store_service import VectorStoreService
from app.utils.link_extractor import LinkExtractor
from app.utils.logger import logger


class AnalysisService:
    """基于分析任务的商品分析服务，负责任务生命周期与结果查询。"""

    # 这里的步骤列表对齐新的草案工作流节点，用于任务进度展示。
    STEP_FLOW = [
        ("resolve_product_context", "解析商品上下文"),
        ("ensure_product_data", "检查商品数据"),
        ("crawling", "抓取商品评论"),
        ("router_agent", "路由分析任务"),
        ("sql_agent", "执行统计分析"),
        ("visual_agent", "生成可视化图表"),
        ("rag_agent", "检索评论证据"),
        ("answer_agent", "汇总候选回答"),
        ("master_agent", "审查最终结果"),
        ("finalize", "收敛最终响应"),
    ]

    ANALYSIS_KEYWORDS = (
        "analyse",
        "analyze",
        "analysis",
        "review",
        "worth",
        "compare",
        "\u5206\u6790",
        "\u8bc4\u4ef7",
        "\u8bc4\u6d4b",
        "\u5dee\u8bc4",
        "\u4f18\u70b9",
        "\u7f3a\u70b9",
        "\u503c\u5f97\u4e70\u5417",
        "\u503c\u5f97\u4e70",
        "\u80fd\u4e70\u5417",
        "\u600e\u4e48\u6837",
    )

    VISUALIZATION_TOOL_SEQUENCE = (
        "score_summary",
        "score_distribution",
        "bad_review_rate",
        "positive_review_rate",
        "score_band_distribution",
        "dimension_stats",
        "dimension_rankings",
        "bad_review_distribution",
        "dimension_coverage",
        "dimension_score_distribution",
        "comment_length_stats",
        "low_score_dimension_pairs",
        "dimension_polarization",
        "monthly_score_trend",
    )

    @staticmethod
    def _dump_protocol_value(value: Any) -> Any:
        """把工作流中的协议对象转换为可安全落库的 JSON 结构。"""
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return value

    @staticmethod
    def _build_visualization_metrics(db: Session, product_id: int) -> dict[str, Any]:
        """执行可视化分析所需的全部 SQL 统计工具。"""
        comments_df = SQLMetricsTools.load_comments_df(db=db, product_id=product_id)
        if comments_df.empty:
            return {}

        metrics: dict[str, Any] = {}
        conn = duckdb.connect(":memory:")
        try:
            conn.register("comments_df", comments_df)
            metrics.update(SQLMetricsTools.get_score_summary(conn))
            metrics.update(SQLMetricsTools.get_score_distribution(conn))
            metrics.update(SQLMetricsTools.get_bad_review_rate(conn))
            metrics.update(SQLMetricsTools.get_positive_review_rate(conn))
            metrics.update(SQLMetricsTools.get_score_band_distribution(conn))
            metrics.update(SQLMetricsTools.get_dimension_stats(conn))
            metrics.update(SQLMetricsTools.get_dimension_rankings(conn))
            metrics.update(SQLMetricsTools.get_bad_review_distribution(conn))
            metrics.update(SQLMetricsTools.get_dimension_coverage(conn))
            metrics.update(SQLMetricsTools.get_dimension_score_distribution(conn))
            metrics.update(SQLMetricsTools.get_comment_length_stats(conn))
            metrics.update(SQLMetricsTools.get_low_score_dimension_pairs(conn))
            metrics.update(SQLMetricsTools.get_dimension_polarization(conn))
            metrics.update(SQLMetricsTools.get_monthly_score_trend(conn))
            return metrics
        finally:
            conn.close()

    @staticmethod
    def _build_visualization_overview(metrics: dict[str, Any]) -> dict[str, Any]:
        """组装商品整体评分和口碑概览。"""
        score_summary = metrics.get("score_summary") or {}
        positive_review = metrics.get("positive_review_rate") or {}
        score_band_distribution = metrics.get("score_band_distribution") or {}
        avg_score = float(score_summary.get("avg_score") or 0)
        bad_review_rate = float(metrics.get("bad_review_rate") or 0)
        total_count = int(score_summary.get("total_count") or 0)
        positive_rate = float(positive_review.get("positive_rate") or 0)

        if total_count == 0:
            summary_text = "当前商品暂无可用于分析的评论数据。"
        elif avg_score >= 4.3 and bad_review_rate <= 0.15:
            summary_text = "整体口碑较强，评论均分高，差评率处于较低水平。"
        elif avg_score >= 3.6 and bad_review_rate <= 0.3:
            summary_text = "整体口碑中等偏上，但仍存在需要重点关注的风险维度。"
        else:
            summary_text = "整体口碑偏弱，差评率或低分问题较为明显，购买前需要谨慎评估。"

        return {
            "total_count": total_count,
            "avg_score": avg_score,
            "bad_review_rate": bad_review_rate,
            "positive_review_rate": positive_rate,
            "score_band_distribution": {
                "positive": int(score_band_distribution.get("positive") or 0),
                "neutral": int(score_band_distribution.get("neutral") or 0),
                "negative": int(score_band_distribution.get("negative") or 0),
            },
            "summary_text": summary_text,
        }

    @staticmethod
    def _build_visualization_dimension_analysis(metrics: dict[str, Any]) -> dict[str, Any]:
        """组装商品维度层面的对比分析结果。"""
        dimension_stats = metrics.get("dimension_stats") or {}
        dimension_rankings = metrics.get("dimension_rankings") or {}
        dimension_coverage = metrics.get("dimension_coverage") or {}
        dimension_score_distribution = metrics.get("dimension_score_distribution") or {}

        best_dimension = None
        weakest_dimension = None
        most_discussed_dimension = None

        if dimension_rankings.get("by_avg_score"):
            best_dimension = dimension_rankings["by_avg_score"][0].get("dimension")
            weakest_dimension = dimension_rankings["by_avg_score"][-1].get("dimension")
        if dimension_rankings.get("by_comment_count"):
            most_discussed_dimension = dimension_rankings["by_comment_count"][0].get("dimension")

        return {
            "dimension_stats": dimension_stats,
            "dimension_rankings": dimension_rankings,
            "dimension_coverage": dimension_coverage,
            "dimension_score_distribution": dimension_score_distribution,
            "best_dimension": best_dimension,
            "weakest_dimension": weakest_dimension,
            "most_discussed_dimension": most_discussed_dimension,
        }

    @staticmethod
    def _build_visualization_risk_analysis(metrics: dict[str, Any]) -> dict[str, Any]:
        """组装差评集中度和两极分化等风险信息。"""
        dimension_stats = metrics.get("dimension_stats") or {}
        bad_review_distribution = metrics.get("bad_review_distribution") or {}
        low_score_dimension_pairs = metrics.get("low_score_dimension_pairs") or []
        dimension_polarization = metrics.get("dimension_polarization") or {}

        high_risk_dimensions = [
            dimension
            for dimension, values in dimension_stats.items()
            if float(values.get("bad_review_rate") or 0) >= 0.3 or float(values.get("avg_score") or 0) <= 3.0
        ]
        polarized_dimensions = [
            dimension
            for dimension, values in dimension_polarization.items()
            if float(values.get("polarization_index") or 0) >= 0.55
        ]

        return {
            "bad_review_distribution": bad_review_distribution,
            "low_score_dimension_pairs": low_score_dimension_pairs,
            "dimension_polarization": dimension_polarization,
            "high_risk_dimensions": high_risk_dimensions,
            "polarized_dimensions": polarized_dimensions,
        }

    @staticmethod
    def _build_visualization_trend_analysis(metrics: dict[str, Any]) -> dict[str, Any]:
        """组装时间趋势和评论长度等辅助分析结果。"""
        monthly_score_trend = metrics.get("monthly_score_trend") or []
        comment_length_stats = metrics.get("comment_length_stats") or {}

        if len(monthly_score_trend) < 2:
            trend_summary = "评论时间趋势数据不足，暂时无法判断近期口碑变化。"
        else:
            first_avg = float(monthly_score_trend[0].get("avg_score") or 0)
            last_avg = float(monthly_score_trend[-1].get("avg_score") or 0)
            first_bad_rate = float(monthly_score_trend[0].get("bad_review_rate") or 0)
            last_bad_rate = float(monthly_score_trend[-1].get("bad_review_rate") or 0)
            if last_avg > first_avg and last_bad_rate <= first_bad_rate:
                trend_summary = "近期评分趋势有改善迹象，差评率未继续扩大。"
            elif last_avg < first_avg or last_bad_rate > first_bad_rate:
                trend_summary = "近期评分或差评率出现走弱迹象，建议重点关注最新评论反馈。"
            else:
                trend_summary = "近期评分趋势整体平稳，没有明显恶化或改善信号。"

        return {
            "monthly_score_trend": monthly_score_trend,
            "comment_length_stats": comment_length_stats,
            "trend_summary": trend_summary,
        }

    @staticmethod
    def _build_visualization_suggestions(
        overview: dict[str, Any],
        dimension_analysis: dict[str, Any],
        risk_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        """基于核心统计指标给出规则化购买建议。"""
        avg_score = float(overview.get("avg_score") or 0)
        bad_review_rate = float(overview.get("bad_review_rate") or 0)
        best_dimension = dimension_analysis.get("best_dimension")
        weakest_dimension = dimension_analysis.get("weakest_dimension")
        most_discussed_dimension = dimension_analysis.get("most_discussed_dimension")
        high_risk_dimensions = risk_analysis.get("high_risk_dimensions") or []
        polarized_dimensions = risk_analysis.get("polarized_dimensions") or []

        strengths: list[str] = []
        risks: list[str] = []
        suitable_for: list[str] = []

        if best_dimension:
            strengths.append(f"{best_dimension} 维度表现最好，适合重点看重这一项体验的用户。")
            suitable_for.append(f"重视 {best_dimension} 体验的用户")
        if most_discussed_dimension and most_discussed_dimension != best_dimension:
            strengths.append(f"{most_discussed_dimension} 是讨论最集中的维度，信息量较充分，便于做购买判断。")

        if weakest_dimension:
            risks.append(f"{weakest_dimension} 是当前最弱维度，购买前应重点阅读相关差评。")
        for dimension in high_risk_dimensions[:3]:
            risks.append(f"{dimension} 维度差评率偏高，存在明显踩坑风险。")
        for dimension in polarized_dimensions[:2]:
            risks.append(f"{dimension} 维度存在明显两极分化，用户体验稳定性不足。")

        if avg_score >= 4.3 and bad_review_rate <= 0.15:
            recommendation_level = "推荐购买"
            purchase_advice = "整体评价稳定，差评占比较低，如果商品满足你的核心功能需求，可以优先考虑购买。"
        elif avg_score >= 3.6 and bad_review_rate <= 0.3:
            recommendation_level = "谨慎购买"
            purchase_advice = "整体口碑尚可，但存在局部风险维度。建议结合你的核心关注点逐项核对后再决定是否购买。"
        else:
            recommendation_level = "不推荐"
            purchase_advice = "整体风险偏高，尤其是差评率或低分维度表现不佳，更建议继续对比同类商品。"

        if not strengths:
            strengths.append("当前商品在已有评论中没有形成特别突出的优势维度。")
        if not risks:
            risks.append("当前评论中没有发现特别突出的高风险维度，但仍建议查看最新差评。")
        if not suitable_for:
            suitable_for.append("愿意继续结合详细评论做二次判断的用户")

        return {
            "strengths": strengths,
            "risks": risks,
            "purchase_advice": purchase_advice,
            "recommendation_level": recommendation_level,
            "suitable_for": suitable_for,
        }

    @staticmethod
    def _build_visualization_charts(metrics: dict[str, Any]) -> list[dict[str, Any]]:
        """把统计结果转换为前端可直接渲染的图表配置。"""
        charts: list[dict[str, Any]] = []
        score_distribution = metrics.get("score_distribution") or {}
        score_band_distribution = metrics.get("score_band_distribution") or {}
        dimension_stats = metrics.get("dimension_stats") or {}
        dimension_score_distribution = metrics.get("dimension_score_distribution") or {}
        bad_review_distribution = metrics.get("bad_review_distribution") or {}
        monthly_score_trend = metrics.get("monthly_score_trend") or []
        dimension_polarization = metrics.get("dimension_polarization") or {}

        if score_distribution:
            charts.append({
                "chart_id": "score_distribution",
                "chart_type": "bar",
                "title": "评分分布",
                "description": "展示 1 到 5 分评论的数量分布。",
                "x_axis": [str(index) for index in range(1, 6)],
                "series": [{"name": "评论数量", "data": [int(score_distribution.get(index, 0)) for index in range(1, 6)]}],
            })

        if score_band_distribution:
            charts.append({
                "chart_id": "score_band_distribution",
                "chart_type": "pie",
                "title": "好中差评占比",
                "description": "展示正向、中性、负向评论的整体占比。",
                "x_axis": ["好评", "中评", "差评"],
                "series": [{
                    "name": "评论数量",
                    "data": [
                        {"name": "好评", "value": int(score_band_distribution.get("positive", 0))},
                        {"name": "中评", "value": int(score_band_distribution.get("neutral", 0))},
                        {"name": "差评", "value": int(score_band_distribution.get("negative", 0))},
                    ],
                }],
            })

        if dimension_stats:
            dimensions = list(dimension_stats.keys())
            charts.append({
                "chart_id": "dimension_avg_score_radar",
                "chart_type": "radar",
                "title": "维度体验雷达图",
                "description": "用雷达图快速比较各维度的整体评分表现。",
                "x_axis": dimensions,
                "series": [{"name": "平均分", "data": [float(dimension_stats[item].get("avg_score", 0)) for item in dimensions]}],
            })
            charts.append({
                "chart_id": "dimension_bad_review_rate",
                "chart_type": "line",
                "title": "维度差评率趋势线",
                "description": "用折线观察各维度差评率高低，识别风险维度。",
                "x_axis": dimensions,
                "series": [{"name": "差评率", "data": [round(float(dimension_stats[item].get("bad_review_rate", 0)) * 100, 2) for item in dimensions]}],
            })
            charts.append({
                "chart_id": "dimension_comment_count",
                "chart_type": "line",
                "title": "维度评论热度",
                "description": "展示各维度被讨论的热度差异。",
                "x_axis": dimensions,
                "series": [{"name": "评论量", "data": [int(dimension_stats[item].get("comment_count", 0)) for item in dimensions]}],
            })

        if dimension_score_distribution:
            dimensions = list(dimension_score_distribution.keys())
            charts.append({
                "chart_id": "dimension_score_distribution",
                "chart_type": "stacked_bar",
                "title": "维度评分结构分布",
                "description": "展示各维度内部 1 到 5 分评论的构成比例，帮助判断分化情况。",
                "x_axis": dimensions,
                "series": [
                    {
                        "name": f"{score}分",
                        "data": [int(dimension_score_distribution[item].get(str(score), 0)) for item in dimensions],
                    }
                    for score in range(1, 6)
                ],
            })

        if bad_review_distribution:
            dimensions = list(bad_review_distribution.keys())
            charts.append({
                "chart_id": "bad_review_distribution",
                "chart_type": "pie",
                "title": "差评维度占比",
                "description": "展示差评主要集中在哪些维度。",
                "x_axis": dimensions,
                "series": [{
                    "name": "差评数量",
                    "data": [{"name": item, "value": int(bad_review_distribution[item])} for item in dimensions],
                }],
            })

        if monthly_score_trend:
            charts.append({
                "chart_id": "monthly_avg_score_trend",
                "chart_type": "line",
                "title": "月度平均分趋势",
                "description": "观察近期评分是否改善或走弱。",
                "x_axis": [str(item.get("month", "")) for item in monthly_score_trend],
                "series": [{"name": "平均分", "data": [float(item.get("avg_score", 0)) for item in monthly_score_trend]}],
            })
            charts.append({
                "chart_id": "monthly_bad_review_rate_trend",
                "chart_type": "line",
                "title": "月度差评率趋势",
                "description": "观察近期差评率变化趋势。",
                "x_axis": [str(item.get("month", "")) for item in monthly_score_trend],
                "series": [{"name": "差评率", "data": [round(float(item.get("bad_review_rate", 0)) * 100, 2) for item in monthly_score_trend]}],
            })

        if dimension_polarization:
            dimensions = list(dimension_polarization.keys())
            charts.append({
                "chart_id": "dimension_polarization",
                "chart_type": "bar",
                "title": "维度两极分化指数",
                "description": "指数越高，说明该维度的高低分分化越明显。",
                "x_axis": dimensions,
                "series": [{"name": "极化指数", "data": [float(dimension_polarization[item].get("polarization_index", 0)) for item in dimensions]}],
            })

        return charts

    @staticmethod
    def _find_product_by_url(db: Session, product_url: str) -> Product | None:
        """根据商品链接解析并查找已存在的商品记录。"""
        link_info = LinkExtractor.extract_from_text(product_url)
        if link_info:
            product = db.query(Product).filter(
                Product.source == link_info["platform"],
                Product.external_product_id == link_info["product_id"],
            ).first()
            if product is not None:
                return product

        return db.query(Product).filter(Product.product_url == product_url).first()

    @staticmethod
    def get_product_visualization(db: Session, user_id: int, product_url: str) -> dict[str, Any]:
        """根据商品链接返回同步商品可视化分析结果。"""
        _ = user_id
        product = AnalysisService._find_product_by_url(db, product_url.strip())
        if product is None:
            return {
                "exists": False,
                "has_data": False,
                "reason": "未找到对应商品数据。",
                "product": None,
                "overview": None,
                "dimension_analysis": None,
                "risk_analysis": None,
                "trend_analysis": None,
                "suggestions": None,
                "charts": [],
                "raw_metrics": None,
            }

        comment_count = db.query(Comment).filter(Comment.product_id == product.id).count()
        product_payload = {
            "product_id": product.id,
            "source": product.source,
            "external_product_id": product.external_product_id,
            "product_name": product.product_name,
        }
        if comment_count == 0:
            return {
                "exists": True,
                "has_data": False,
                "reason": "商品存在，但当前没有可用于统计分析的评论数据。",
                "product": product_payload,
                "overview": None,
                "dimension_analysis": None,
                "risk_analysis": None,
                "trend_analysis": None,
                "suggestions": None,
                "charts": [],
                "raw_metrics": None,
            }

        raw_metrics = AnalysisService._build_visualization_metrics(db, product.id)
        if not raw_metrics:
            return {
                "exists": True,
                "has_data": False,
                "reason": "商品存在，但当前没有可用于统计分析的评论数据。",
                "product": product_payload,
                "overview": None,
                "dimension_analysis": None,
                "risk_analysis": None,
                "trend_analysis": None,
                "suggestions": None,
                "charts": [],
                "raw_metrics": None,
            }

        overview = AnalysisService._build_visualization_overview(raw_metrics)
        dimension_analysis = AnalysisService._build_visualization_dimension_analysis(raw_metrics)
        risk_analysis = AnalysisService._build_visualization_risk_analysis(raw_metrics)
        trend_analysis = AnalysisService._build_visualization_trend_analysis(raw_metrics)
        suggestions = AnalysisService._build_visualization_suggestions(
            overview=overview,
            dimension_analysis=dimension_analysis,
            risk_analysis=risk_analysis,
        )
        charts = AnalysisService._build_visualization_charts(raw_metrics)

        return {
            "exists": True,
            "has_data": True,
            "reason": None,
            "product": product_payload,
            "overview": overview,
            "dimension_analysis": dimension_analysis,
            "risk_analysis": risk_analysis,
            "trend_analysis": trend_analysis,
            "suggestions": suggestions,
            "charts": charts,
            "raw_metrics": raw_metrics,
        }

    @staticmethod
    def _build_final_response(workflow_state: dict[str, Any]) -> FinalAnalysisResponse:
        """根据工作流产物组装最终响应，保持前端消费结构稳定。"""
        answer_draft = workflow_state.get("answer_draft")
        visual_result = workflow_state.get("visual_result")
        product_context = workflow_state.get("product_context")
        return FinalAnalysisResponse(
            answer=answer_draft.answer if answer_draft is not None else "",
            charts=visual_result.charts if visual_result is not None else [],
            meta=FinalResponseMeta(
                product_id=product_context.product_id if product_context is not None else None,
                used_agents=[
                    "router_agent",
                    *(["sql_agent"] if workflow_state.get("sql_result") is not None else []),
                    *(["visual_agent"] if visual_result is not None and visual_result.charts else []),
                    *(["rag_agent"] if workflow_state.get("rag_result") is not None else []),
                    "answer_agent",
                    "master_agent",
                ],
                retry_count=workflow_state.get("retry_count", 0),
            ),
        )

    @staticmethod
    def _set_task_state(
        db: Session,
        task: AnalysisTask,
        *,
        status: AnalysisTaskStatus | None = None,
        current_step: str | None = None,
        progress: int | None = None,
        error_message: str | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> AnalysisTask:
        """统一更新分析任务状态，并把进度与失败原因持久化到数据库。"""
        if status is not None:
            task.status = status
        if current_step is not None:
            task.current_step = current_step
        if progress is not None:
            task.progress = progress
        if error_message is not None or status == AnalysisTaskStatus.FAILED:
            task.error_message = error_message
        if started and task.started_at is None:
            task.started_at = datetime.now(timezone.utc)
        if finished:
            task.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(task)
        logger.info(
            "Analysis task state updated: task_id={} status={} step={} progress={}",
            task.task_id,
            task.status.value,
            task.current_step,
            task.progress,
        )
        return task

    @staticmethod
    def _contains_analysis_intent(text: str) -> bool:
        """判断一条消息是否包含分析意图，用于复用会话已绑定商品。"""
        lowered = text.lower()
        return any(keyword in lowered for keyword in AnalysisService.ANALYSIS_KEYWORDS)

    @staticmethod
    def _get_or_create_product(db: Session, link_info: dict[str, str]) -> Product:
        """根据链接解析结果获取已有商品，必要时创建新的商品记录。"""
        product = db.query(Product).filter(
            Product.source == link_info["platform"],
            Product.external_product_id == link_info["product_id"],
        ).first()
        if product:
            if not product.product_url:
                product.product_url = link_info["url"]
            return product

        product = Product(
            source=link_info["platform"],
            external_product_id=link_info["product_id"],
            product_url=link_info["url"],
            crawl_status=ProductStatus.PENDING,
        )
        db.add(product)
        db.flush()
        logger.info(f"Created product {product.id} for {product.source}:{product.external_product_id}")
        return product

    @staticmethod
    def resolve_product_for_message(db: Session, conversation: Conversation, content: str) -> Product | None:
        """解析当前消息对应的商品对象，优先使用链接，其次回退到会话绑定商品。"""
        link_info = LinkExtractor.extract_from_text(content)
        if link_info:
            return AnalysisService._get_or_create_product(db, link_info)

        if conversation.bound_product_id and AnalysisService._contains_analysis_intent(content):
            return db.query(Product).filter(Product.id == conversation.bound_product_id).first()

        return None

    @staticmethod
    def find_reusable_task(
        db: Session,
        user_id: int,
        conversation_id: int,
        product_id: int,
        question: str,
    ) -> AnalysisTask | None:
        """查找同会话、同商品、同问题下仍可复用的分析任务。"""
        normalized_question = question.strip()
        task = db.query(AnalysisTask).filter(
            AnalysisTask.user_id == user_id,
            AnalysisTask.conversation_id == conversation_id,
            AnalysisTask.product_id == product_id,
            AnalysisTask.question == normalized_question,
            AnalysisTask.status.in_([AnalysisTaskStatus.PENDING, AnalysisTaskStatus.PROCESSING]),
        ).order_by(AnalysisTask.created_at.desc()).first()
        if task is not None:
            logger.info(
                "Reusable analysis task found: task_id={} conversation_id={} product_id={}",
                task.task_id,
                conversation_id,
                product_id,
            )
        return task

    @staticmethod
    def _infer_product_resolved_from(task: AnalysisTask) -> str:
        """根据任务问题与绑定商品，推断本次商品上下文来源。"""
        if getattr(task, "product_id", None) is None:
            return "none"
        question = getattr(task, "question", "") or ""
        return "message_link" if LinkExtractor.extract_from_text(question) else "bound_product"

    @staticmethod
    def _ensure_vector_ready(db: Session, product_id: int) -> bool:
        """检查并补齐商品评论向量索引，返回当前向量是否可用于检索。"""
        total_comments = db.query(Comment).filter(
            Comment.product_id == product_id,
            Comment.content.isnot(None),
        ).count()
        if total_comments == 0:
            return False

        pending_count = db.query(Comment).filter(
            Comment.product_id == product_id,
            Comment.content.isnot(None),
            Comment.is_vectorized.is_(False),
        ).count()
        if pending_count > 0:
            VectorStoreService.ensure_product_vectorized(db, product_id)

        remaining_pending = db.query(Comment).filter(
            Comment.product_id == product_id,
            Comment.content.isnot(None),
            Comment.is_vectorized.is_(False),
        ).count()
        return remaining_pending == 0

    @staticmethod
    def create_task_for_message(
        db: Session,
        user_id: int,
        conversation: Conversation,
        user_message: Message,
        product: Product | None,
        question: str,
    ) -> AnalysisTask:
        """为已落库的用户消息创建统一分析任务，并在有商品时绑定当前商品。"""
        if product is not None:
            conversation.bound_product_id = product.id
        task = AnalysisTask(
            task_id=str(uuid.uuid4()),
            user_id=user_id,
            conversation_id=conversation.id,
            product_id=product.id if product is not None else conversation.bound_product_id,
            trigger_message_id=user_message.id,
            question=question,
            status=AnalysisTaskStatus.PENDING,
            current_step="resolve_product_context",
            progress=10,
        )
        db.add(task)
        db.flush()
        logger.info(
            "Analysis task created: task_id={} conversation_id={} product_id={} trigger_message_id={}",
            task.task_id,
            conversation.id,
            task.product_id,
            user_message.id,
        )
        return task

    @staticmethod
    def _build_result_message_content(task: AnalysisTask, report: AnalysisReport) -> str:
        """构造写回会话的分析结果消息内容。"""
        product = task.product
        final_response = (report.statistics_json or {}).get("final_response") or {}
        summary_text = report.summary or final_response.get("answer") or "No summary generated."
        sql_result = (report.statistics_json or {}).get("sql_result") or {}
        score_summary = sql_result.get("metrics", {}).get("score_summary") or {}
        total_count = score_summary.get("total_count", 0)
        avg_score = score_summary.get("avg_score", 0)
        return (
            f"Analysis completed for product {product.external_product_id}.\n"
            f"Task ID: {task.task_id}\n"
            f"Report ID: {report.id}\n"
            f"Total comments: {total_count}\n"
            f"Average score: {avg_score}\n"
            f"Summary: {summary_text}"
        )

    @staticmethod
    def _upsert_result_message(db: Session, task: AnalysisTask, report: AnalysisReport) -> Message | None:
        """将分析结果消息写回会话，如果已存在则更新。"""
        if task.conversation_id is None:
            logger.warning("Skip result message because conversation_id is missing: task_id={}", task.task_id)
            return None

        marker = f"Task ID: {task.task_id}"
        existing_messages = db.query(Message).filter(
            Message.conversation_id == task.conversation_id,
            Message.role == MessageRole.ASSISTANT,
            Message.message_type == MessageType.ANALYSIS_RESULT,
        ).all()
        result_message = next((item for item in existing_messages if marker in item.content), None)
        if result_message is None:
            result_message = Message(
                conversation_id=task.conversation_id,
                role=MessageRole.ASSISTANT,
                message_type=MessageType.ANALYSIS_RESULT,
                content="",
            )
            db.add(result_message)

        result_message.content = AnalysisService._build_result_message_content(task, report)
        conversation = db.query(Conversation).filter(Conversation.id == task.conversation_id).first()
        if conversation is not None:
            conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(result_message)
        logger.info(
            "Analysis result message saved: task_id={} message_id={} conversation_id={}",
            task.task_id,
            result_message.id,
            task.conversation_id,
        )
        return result_message

    @staticmethod
    def _upsert_failure_message(db: Session, task: AnalysisTask, error_message: str) -> Message | None:
        """将分析失败消息写回会话，如果已存在则更新。"""
        if task.conversation_id is None:
            logger.warning("Skip failure message because conversation_id is missing: task_id={}", task.task_id)
            return None

        marker = f"Task ID: {task.task_id}"
        existing_messages = db.query(Message).filter(
            Message.conversation_id == task.conversation_id,
            Message.role == MessageRole.SYSTEM,
            Message.message_type == MessageType.SYSTEM_NOTICE,
        ).all()
        failure_message = next(
            (
                item for item in existing_messages
                if marker in item.content and "Analysis failed" in item.content
            ),
            None,
        )
        if failure_message is None:
            failure_message = Message(
                conversation_id=task.conversation_id,
                role=MessageRole.SYSTEM,
                message_type=MessageType.SYSTEM_NOTICE,
                content="",
            )
            db.add(failure_message)

        failure_message.content = (
            "Analysis failed.\n"
            f"Task ID: {task.task_id}\n"
            f"Current step: {task.current_step or 'unknown'}\n"
            f"Reason: {error_message}"
        )
        conversation = db.query(Conversation).filter(Conversation.id == task.conversation_id).first()
        if conversation is not None:
            conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(failure_message)
        logger.info(
            "Analysis failure message saved: task_id={} message_id={} conversation_id={}",
            task.task_id,
            failure_message.id,
            task.conversation_id,
        )
        return failure_message

    @staticmethod
    def _upsert_report_from_workflow(
        db: Session,
        task: AnalysisTask,
        workflow_state: dict[str, Any],
    ) -> AnalysisReport:
        """把工作流结果写回分析报告，并同步兼容前端查询结构。"""
        product_context = workflow_state.get("product_context")
        data_context = workflow_state.get("data_context")
        final_response = AnalysisService._build_final_response(workflow_state)
        route_decision = workflow_state.get("route_decision")
        sql_result = workflow_state.get("sql_result")
        visual_result = workflow_state.get("visual_result")
        rag_result = workflow_state.get("rag_result")
        answer_draft = workflow_state.get("answer_draft")
        master_decision = workflow_state.get("master_decision")
        retry_count = workflow_state.get("retry_count", 0)

        summary = final_response.answer
        evidence_json = [item.model_dump() for item in rag_result.evidence] if rag_result is not None else []
        report_stats = {
            "product_context": AnalysisService._dump_protocol_value(product_context),
            "data_context": AnalysisService._dump_protocol_value(data_context),
            "route_decision": AnalysisService._dump_protocol_value(route_decision),
            "sql_result": AnalysisService._dump_protocol_value(sql_result),
            "visual_result": AnalysisService._dump_protocol_value(visual_result),
            "rag_result": AnalysisService._dump_protocol_value(rag_result),
            "answer_draft": AnalysisService._dump_protocol_value(answer_draft),
            "master_decision": AnalysisService._dump_protocol_value(master_decision),
            "final_response": final_response.model_dump(),
            "retry_count": retry_count,
        }

        report = task.report
        if report is None:
            report = AnalysisReport(
                analysis_task_id=task.id,
                user_id=task.user_id,
                product_id=task.product_id,
                conversation_id=task.conversation_id,
            )
            db.add(report)

        report.summary = summary
        report.statistics_json = report_stats
        report.charts_config = None
        report.evidence_json = evidence_json
        db.commit()
        db.refresh(report)
        logger.info(
            "Analysis report saved: task_id={} report_id={} used_agents={}",
            task.task_id,
            report.id,
            final_response.meta.used_agents,
        )
        AnalysisService._upsert_result_message(db, task, report)
        return report

    @staticmethod
    def process_task(task_id: str) -> None:
        """在后台执行分析任务，并通过多 Agent 工作流产出最终协议结果。"""
        db = SessionLocal()
        try:
            task = db.query(AnalysisTask).filter(AnalysisTask.task_id == task_id).first()
            if task is None:
                logger.error(f"Background analysis task not found: task_id={task_id}")
                return
            if task.status not in {AnalysisTaskStatus.PENDING, AnalysisTaskStatus.PROCESSING}:
                logger.warning(
                    "Skip background execution for task_id={} because status={}",
                    task.task_id,
                    task.status.value,
                )
                return

            logger.info(
                "Background analysis started: task_id={} product_id={} conversation_id={}",
                task.task_id,
                task.product_id,
                task.conversation_id,
            )
            runtime = AnalysisWorkflowRuntime(
                db=db,
                task=task,
                set_task_state_fn=AnalysisService._set_task_state,
                should_crawl_fn=AnalysisService._should_crawl,
                crawl_product_fn=CrawlerService.crawl_product,
                ensure_vector_ready_fn=AnalysisService._ensure_vector_ready,
                product_resolved_from=AnalysisService._infer_product_resolved_from(task),
            )
            workflow_state = AnalysisWorkflow.run(
                {
                    "user_message": task.question,
                },
                runtime=runtime,
            )
            AnalysisService._upsert_report_from_workflow(db, task, workflow_state)
            AnalysisService._set_task_state(
                db,
                task,
                status=AnalysisTaskStatus.COMPLETED,
                current_step="finalize",
                progress=100,
                finished=True,
            )
            logger.info("Background analysis completed: task_id={}", task.task_id)
        except Exception as exc:
            logger.exception(f"Background analysis failed: task_id={task_id} error={exc}")
            try:
                # 工作流内部若已发生 flush/commit 异常，Session 会进入 PendingRollback 状态。
                # 这里必须先 rollback，才能继续查询任务并回写 FAILED 状态。
                db.rollback()
                task = db.query(AnalysisTask).filter(AnalysisTask.task_id == task_id).first()
                if task is not None:
                    AnalysisService._set_task_state(
                        db,
                        task,
                        status=AnalysisTaskStatus.FAILED,
                        current_step=task.current_step or "ensure_product_data",
                        progress=task.progress,
                        error_message=str(exc),
                        finished=True,
                    )
                    AnalysisService._upsert_failure_message(db, task, str(exc))
            except Exception as state_error:
                logger.exception(f"Failed to mark task as failed: task_id={task_id} error={state_error}")
        finally:
            db.close()

    @staticmethod
    def _should_crawl(product: Product) -> bool:
        """判断商品数据是否需要重新抓取，并兼容数据库中的无时区时间。"""
        # 超过 3 天未抓取则视为数据过期，需要重新触发采集。
        if product.last_crawled_at is None:
            return True
        last_crawled_at = product.last_crawled_at
        if last_crawled_at.tzinfo is None:
            last_crawled_at = last_crawled_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - last_crawled_at).days > 3

    @staticmethod
    def get_task_by_task_id(db: Session, user_id: int, task_id: str) -> AnalysisTask:
        """按任务 ID 获取任务，并校验该任务属于当前用户。"""
        task = db.query(AnalysisTask).filter(
            AnalysisTask.task_id == task_id,
            AnalysisTask.user_id == user_id,
        ).first()
        if not task:
            raise ValueError(f"Analysis task not found: {task_id}")
        return task

    @staticmethod
    def retry_task(db: Session, user_id: int, task_id: str) -> AnalysisTask:
        """把失败任务重置为待执行状态，供上层重新调度。"""
        task = AnalysisService.get_task_by_task_id(db, user_id, task_id)
        if task.status != AnalysisTaskStatus.FAILED:
            raise ValueError(f"Only failed tasks can be retried: {task_id}")

        task.status = AnalysisTaskStatus.PENDING
        task.current_step = "resolve_product_context"
        task.progress = 0
        task.error_message = None
        task.started_at = None
        task.finished_at = None
        db.commit()
        db.refresh(task)
        logger.info(
            "Analysis task reset for retry: task_id={} conversation_id={} product_id={}",
            task.task_id,
            task.conversation_id,
            task.product_id,
        )
        return task

    @staticmethod
    def get_task_progress(db: Session, user_id: int, task_id: str) -> dict[str, Any]:
        """返回任务当前进度，并把数据库中的失败原因一并暴露给前端。"""
        task = AnalysisService.get_task_by_task_id(db, user_id, task_id)
        current_index = next(
            (index for index, (step, _) in enumerate(AnalysisService.STEP_FLOW) if step == task.current_step),
            -1,
        )
        steps = []
        for index, (step, label) in enumerate(AnalysisService.STEP_FLOW):
            if task.status == AnalysisTaskStatus.FAILED and step == task.current_step:
                step_status = "failed"
            elif task.status == AnalysisTaskStatus.COMPLETED or index < current_index:
                step_status = "completed"
            elif index == current_index and task.status == AnalysisTaskStatus.PROCESSING:
                step_status = "processing"
            else:
                step_status = "pending"
            steps.append(
                {
                    "step": step,
                    "label": label,
                    "status": step_status,
                }
            )

        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "current_step": task.current_step,
            "progress": task.progress,
            "steps": steps,
            "report_ready": task.report is not None,
            "error_message": task.error_message,
        }

    @staticmethod
    def get_task_result(db: Session, user_id: int, task_id: str) -> dict[str, Any]:
        """返回任务最终结果；若任务失败或未完成，则返回持久化任务状态。"""
        task = AnalysisService.get_task_by_task_id(db, user_id, task_id)
        if task.status != AnalysisTaskStatus.COMPLETED or task.report is None:
            return {
                "task_id": task.task_id,
                "status": task.status.value,
                "progress": task.progress,
                "current_step": task.current_step,
                "error_message": task.error_message,
                "result_ready": False,
            }

        report = task.report
        product = task.product
        statistics = report.statistics_json or {}
        product_context = statistics.get("product_context")
        data_context = statistics.get("data_context")
        final_response = statistics.get("final_response") or {}
        route_decision = statistics.get("route_decision")
        sql_result = statistics.get("sql_result")
        visual_result = statistics.get("visual_result")
        rag_result = statistics.get("rag_result")
        answer_draft = statistics.get("answer_draft")
        master_decision = statistics.get("master_decision")
        retry_count = statistics.get("retry_count", 0)
        evidence_items: list[dict[str, Any]] = []
        if isinstance(report.evidence_json, list):
            for item in report.evidence_json:
                if isinstance(item, dict):
                    evidence_items.append(
                        {
                            "content": item.get("content", ""),
                            "score": item.get("score"),
                            "dimension": item.get("dimension"),
                            "similarity": item.get("similarity"),
                        }
                    )

        return {
            "report_id": report.id,
            "task_id": task.task_id,
            "conversation_id": report.conversation_id,
            "product": (
                {
                    "product_id": product.id,
                    "source": product.source,
                    "external_product_id": product.external_product_id,
                    "product_name": product.product_name,
                }
                if product is not None else None
            ),
            "product_context": product_context,
            "data_context": data_context,
            "final_response": final_response,
            "route_decision": route_decision,
            "sql_result": sql_result,
            "visual_result": visual_result,
            "rag_result": rag_result,
            "answer_draft": answer_draft,
            "master_decision": master_decision,
            "retry_count": retry_count,
            "evidence": evidence_items,
            "created_at": report.created_at,
            "result_ready": True,
        }
