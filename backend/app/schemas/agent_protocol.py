"""Structured protocol models for the multi-agent analysis workflow."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResponseStyle(str, Enum):
    BRIEF_ANSWER = "brief_answer"
    PROFESSIONAL_ANALYSIS = "professional_analysis"
    REPORT_STYLE = "report_style"


class MasterDecisionType(str, Enum):
    PASS = "pass"
    RETRY = "retry"
    FALLBACK_PASS = "fallback_pass"
    FAIL = "fail"


class RetryFromAgent(str, Enum):
    ROUTER_AGENT = "router_agent"
    SQL_AGENT = "sql_agent"
    VISUAL_AGENT = "visual_agent"
    RAG_AGENT = "rag_agent"
    ANSWER_AGENT = "answer_agent"


class SupportedChartType(str, Enum):
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"
    RADAR = "radar"
    STACKED_BAR = "stacked_bar"


class ProductContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_product: bool = Field(..., description="请求是否绑定某个商品")
    source: str | None = Field(default=None, description="平台")
    external_product_id: str | None = Field(default=None, description="平台产品id")
    product_id: int | None = Field(default=None, description="内部产品id")
    resolved_from: str = Field(..., description="message_link / bound_product / none")


class DataContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_ready: bool = Field(..., description="Whether data is ready for downstream analysis")
    used_cache: bool = Field(..., description="Whether cached crawl result was reused")
    crawler_triggered: bool = Field(..., description="Whether crawler was triggered in this run")
    vector_ready: bool = Field(..., description="Whether vector store is ready")
    last_crawled_at: str | None = Field(default=None, description="ISO datetime of last successful crawl")
    comment_count: int = Field(default=0, description="Current persisted comment count for the product")
    data_issue: str | None = Field(default=None, description="Reason why data preparation is incomplete")


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need_sql: bool
    need_rag: bool
    need_visual: bool
    response_style: ResponseStyle
    reason: str


class SQLToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class SQLToolPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_calls: list[SQLToolCall] = Field(default_factory=list)


class SQLAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_calls: list[SQLToolCall] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    description: str


class ChartSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    data: list[Any] = Field(default_factory=list)


class ChartSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_id: str
    chart_type: SupportedChartType
    title: str
    description: str | None = None
    x_axis: list[str | int | float] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)


class VisualAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    charts: list[ChartSpec] = Field(default_factory=list)


class RAGQueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[str] = Field(default_factory=list)


class RAGEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    dimension: str | None = None
    score: int | float | None = None
    similarity: float | None = None


class RAGAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[str] = Field(default_factory=list)
    evidence: list[RAGEvidenceItem] = Field(default_factory=list)
    insight: str
    insight_points: list[str] = Field(default_factory=list)


class AnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    answer_points: list[str] = Field(default_factory=list)


class MasterDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: MasterDecisionType
    reason: str
    missing_items: list[str] = Field(default_factory=list)
    retry_from: RetryFromAgent | None = None


class FinalResponseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int | None = None
    used_agents: list[str] = Field(default_factory=list)
    retry_count: int = 0


class FinalAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    charts: list[ChartSpec] = Field(default_factory=list)
    meta: FinalResponseMeta
