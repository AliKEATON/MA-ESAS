"""多 Agent 工作流共享状态与运行时上下文定义。"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, TypedDict

from app.schemas.agent_protocol import (
    AnswerDraft,
    DataContext,
    MasterDecision,
    ProductContext,
    RAGAgentResult,
    RouteDecision,
    SQLAgentResult,
    VisualAgentResult,
)


class MultiAgentAnalysisState(TypedDict, total=False):
    """统一承载多 Agent 工作流中的业务状态与中间产物。"""

    # 基础请求上下文
    user_message: str

    # 重试控制
    retry_count: int
    max_retry: int

    # 协议化中间状态
    product_context: ProductContext
    data_context: DataContext
    route_decision: RouteDecision
    sql_result: SQLAgentResult
    visual_result: VisualAgentResult
    rag_result: RAGAgentResult
    answer_draft: AnswerDraft
    master_decision: MasterDecision


@dataclass(slots=True)
class AnalysisWorkflowRuntime:
    """封装工作流运行时依赖，避免把数据库与回调混入业务状态。"""

    db: Any
    task: Any
    set_task_state_fn: Callable[..., Any]
    should_crawl_fn: Callable[[Any], bool]
    crawl_product_fn: Callable[[Any, int], Any]
    ensure_vector_ready_fn: Callable[[Any, int], bool] | None = None
    product_resolved_from: str = "none"
