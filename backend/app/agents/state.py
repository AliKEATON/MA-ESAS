"""多 Agent 工作流共享状态定义。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from app.schemas.agent_protocol import (
    AnswerDraft,
    DataContext,
    FinalAnalysisResponse,
    MasterDecision,
    ProductContext,
    RAGAgentResult,
    RouteDecision,
    SQLAgentResult,
    VisualAgentResult,
)


class MultiAgentAnalysisState(TypedDict, total=False):
    """统一承载多 Agent 工作流上下文与中间产物。"""

    # 基础请求上下文
    user_id: int
    conversation_id: int | None
    user_message: str
    task_id: str

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
    final_response: FinalAnalysisResponse

    # 运行时依赖
    db: Any
    task: Any
    error_message: str | None

    # 服务层注入的回调，便于工作流内部更新任务状态与触发采集
    set_task_state_fn: Callable[..., Any]
    should_crawl_fn: Callable[[Any], bool]
    crawl_product_fn: Callable[[Any, int], Any]
    ensure_vector_ready_fn: Callable[[Any, int], bool]
    product_resolved_from: str
