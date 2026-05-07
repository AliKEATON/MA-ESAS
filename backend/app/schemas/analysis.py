"""
分析任务相关 Pydantic Schema
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AnalysisTaskStatus(str, Enum):
    """分析任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisStepStatus(str, Enum):
    """分析步骤状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisTaskStepResponse(BaseModel):
    """单个步骤状态"""
    step: str
    label: str
    status: AnalysisStepStatus


class AnalysisTaskProgressResponse(BaseModel):
    """任务状态与进度响应"""
    task_id: str
    status: AnalysisTaskStatus
    current_step: str | None
    progress: int
    steps: list[AnalysisTaskStepResponse]
    report_ready: bool
    # 该字段来自 AnalysisTask.error_message，用于向前端暴露任务失败原因。
    error_message: str | None


class AnalysisProductResponse(BaseModel):
    """分析结果中的商品信息"""
    product_id: int
    source: str
    external_product_id: str
    product_name: str | None


class AnalysisEvidenceItem(BaseModel):
    """分析结果中的证据评论"""
    content: str
    score: int | None = None
    dimension: str | None = None
    similarity: float | None = None


class AnalysisResultResponse(BaseModel):
    """分析结果响应"""
    report_id: int
    task_id: str
    conversation_id: int | None
    product: AnalysisProductResponse | None
    product_context: dict[str, Any] | None = None
    data_context: dict[str, Any] | None = None
    final_response: dict[str, Any]
    route_decision: dict[str, Any] | None
    sql_result: dict[str, Any] | None
    visual_result: dict[str, Any] | None = None
    rag_result: dict[str, Any] | None = None
    answer_draft: dict[str, Any] | None = None
    master_decision: dict[str, Any] | None = None
    retry_count: int = 0
    evidence: list[AnalysisEvidenceItem]
    created_at: datetime
    result_ready: bool = True


class ProductVisualizationRequest(BaseModel):
    """商品可视化分析请求。"""
    product_url: str


class ProductVisualizationOverviewResponse(BaseModel):
    """商品可视化分析页的总体概览数据。"""
    total_count: int
    avg_score: float
    bad_review_rate: float
    positive_review_rate: float
    score_band_distribution: dict[str, int]
    summary_text: str


class ProductVisualizationDimensionAnalysisResponse(BaseModel):
    """商品可视化分析页的维度分析结果。"""
    dimension_stats: dict[str, Any]
    dimension_rankings: dict[str, Any]
    dimension_coverage: dict[str, int]
    dimension_score_distribution: dict[str, dict[str, int]]
    best_dimension: str | None = None
    weakest_dimension: str | None = None
    most_discussed_dimension: str | None = None


class ProductVisualizationRiskAnalysisResponse(BaseModel):
    """商品可视化分析页的风险分析结果。"""
    bad_review_distribution: dict[str, int]
    low_score_dimension_pairs: list[dict[str, Any]]
    dimension_polarization: dict[str, Any]
    high_risk_dimensions: list[str]
    polarized_dimensions: list[str]


class ProductVisualizationTrendAnalysisResponse(BaseModel):
    """商品可视化分析页的趋势分析结果。"""
    monthly_score_trend: list[dict[str, Any]]
    comment_length_stats: dict[str, Any]
    trend_summary: str


class ProductVisualizationSuggestionsResponse(BaseModel):
    """商品可视化分析页的购买建议。"""
    strengths: list[str]
    risks: list[str]
    purchase_advice: str
    recommendation_level: str
    suitable_for: list[str]


class ProductVisualizationResponse(BaseModel):
    """商品可视化分析页响应。"""
    exists: bool
    has_data: bool
    reason: str | None = None
    product: AnalysisProductResponse | None = None
    overview: ProductVisualizationOverviewResponse | None = None
    dimension_analysis: ProductVisualizationDimensionAnalysisResponse | None = None
    risk_analysis: ProductVisualizationRiskAnalysisResponse | None = None
    trend_analysis: ProductVisualizationTrendAnalysisResponse | None = None
    suggestions: ProductVisualizationSuggestionsResponse | None = None
    charts: list[dict[str, Any]] = Field(default_factory=list)
    raw_metrics: dict[str, Any] | None = None
