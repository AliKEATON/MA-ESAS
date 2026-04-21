"""
分析任务相关 Pydantic Schema
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


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
