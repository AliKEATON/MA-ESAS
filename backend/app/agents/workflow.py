"""LangGraph 多 Agent 协作工作流编排。"""

from __future__ import annotations

from datetime import timezone
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.answer_agent import AnswerAgent
from app.agents.master_agent import MasterAgent
from app.agents.rag_agent import RAGAgent
from app.agents.router_agent import RouterAgent
from app.agents.sql_agent import SQLAgent
from app.agents.state import MultiAgentAnalysisState
from app.agents.visual_agent import VisualAgent
from app.models import Comment, Product
from app.schemas.agent_protocol import DataContext, FinalAnalysisResponse, FinalResponseMeta, ProductContext, VisualAgentResult


class AnalysisWorkflow:
    """负责按照草案协议编排各分析 Agent 的执行顺序。"""

    _compiled_graph: Any = None

    @classmethod
    def run(cls, state: MultiAgentAnalysisState) -> MultiAgentAnalysisState:
        """执行完整工作流，并返回包含最终协议结果的共享状态。"""
        initial_state = dict(state)
        initial_state.setdefault("retry_count", 0)
        initial_state.setdefault("max_retry", 1)
        if "user_message" not in initial_state and "task" in initial_state:
            task = initial_state["task"]
            if getattr(task, "question", None):
                initial_state["user_message"] = task.question
        return cls._get_graph().invoke(initial_state)

    @classmethod
    def _get_graph(cls) -> Any:
        """延迟编译 LangGraph，避免重复构图。"""
        if cls._compiled_graph is not None:
            return cls._compiled_graph

        graph = StateGraph(MultiAgentAnalysisState)
        for name, handler in (
            ("resolve_product_context", cls._resolve_product_context),
            ("ensure_product_data", cls._ensure_product_data),
            ("router_agent", cls._router_agent),
            ("sql_agent", cls._sql_agent),
            ("visual_agent", cls._visual_agent),
            ("rag_agent", cls._rag_agent),
            ("answer_agent", cls._answer_agent),
            ("master_agent", cls._master_agent),
            ("finalize", cls._finalize),
        ):
            graph.add_node(name, handler)

        graph.set_entry_point("resolve_product_context")
        graph.add_edge("resolve_product_context", "ensure_product_data")
        graph.add_edge("ensure_product_data", "router_agent")
        graph.add_conditional_edges("router_agent", cls._dispatch_after_router, {
            "sql_agent": "sql_agent",
            "rag_agent": "rag_agent",
            "answer_agent": "answer_agent",
        })
        graph.add_conditional_edges("sql_agent", cls._dispatch_after_sql, {
            "visual_agent": "visual_agent",
            "rag_agent": "rag_agent",
            "answer_agent": "answer_agent",
        })
        graph.add_conditional_edges("visual_agent", cls._dispatch_after_visual, {
            "rag_agent": "rag_agent",
            "answer_agent": "answer_agent",
        })
        graph.add_edge("rag_agent", "answer_agent")
        graph.add_edge("answer_agent", "master_agent")
        graph.add_conditional_edges("master_agent", cls._dispatch_after_master, {
            "sql_agent": "sql_agent",
            "visual_agent": "visual_agent",
            "rag_agent": "rag_agent",
            "answer_agent": "answer_agent",
            "finalize": "finalize",
        })
        graph.add_edge("finalize", END)

        cls._compiled_graph = graph.compile()
        return cls._compiled_graph

    @staticmethod
    def _resolve_product_context(state: MultiAgentAnalysisState) -> MultiAgentAnalysisState:
        """解析商品上下文，并同步任务状态到商品解析阶段。"""
        AnalysisWorkflow._mark_step(state, "resolve_product_context", 5, started=True)
        existing = state.get("product_context")
        if existing is not None:
            return {"product_context": existing}

        task = state.get("task")
        product = getattr(task, "product", None)
        product_id = getattr(task, "product_id", None)
        resolved_from = state.get("product_resolved_from", "none")
        if product_id is None:
            if product is not None:
                raise RuntimeError("Task product context is inconsistent: task.product exists but product_id is missing")
            return {
                "product_context": ProductContext(
                    has_product=False,
                    source=None,
                    external_product_id=None,
                    product_id=None,
                    resolved_from="none",
                )
            }

        if product is None:
            raise RuntimeError(f"Task product context is invalid: product_id={product_id} but task.product is missing")
        if getattr(product, "id", None) != product_id:
            raise RuntimeError("Task product context is invalid: task.product.id does not match task.product_id")
        if resolved_from not in {"message_link", "bound_product"}:
            raise RuntimeError(f"Task product context source is invalid: {resolved_from}")
        return {
            "product_context": ProductContext(
                has_product=True,
                source=getattr(product, "source", None),
                external_product_id=getattr(product, "external_product_id", None),
                product_id=product_id,
                resolved_from=resolved_from,
            )
        }

    @staticmethod
    def _ensure_product_data(state: MultiAgentAnalysisState) -> MultiAgentAnalysisState:
        """检查商品数据是否需要重新抓取，并产出数据准备上下文。"""
        AnalysisWorkflow._mark_step(state, "ensure_product_data", 15)
        existing = state.get("data_context")
        if existing is not None:
            return {"data_context": existing}

        product_context = state.get("product_context")
        if product_context is None or not product_context.has_product or product_context.product_id is None:
            return {
                "data_context": DataContext(
                    data_ready=False,
                    used_cache=False,
                    crawler_triggered=False,
                    vector_ready=False,
                    last_crawled_at=None,
                    comment_count=0,
                    data_issue="no_product_context",
                )
            }

        task = state.get("task")
        db = state.get("db")
        if db is None:
            raise RuntimeError("Workflow db session is missing in ensure_product_data")

        product_id = product_context.product_id
        product = db.query(Product).filter(Product.id == product_id).first()
        if product is None:
            raise RuntimeError(f"Product not found during data preparation: product_id={product_id}")
        if getattr(task, "product_id", None) != product_id:
            raise RuntimeError(
                f"Task product mismatch during data preparation: task.product_id={getattr(task, 'product_id', None)} product_context.product_id={product_id}"
            )

        should_crawl_fn = state.get("should_crawl_fn")
        crawl_product_fn = state.get("crawl_product_fn")
        ensure_vector_ready_fn = state.get("ensure_vector_ready_fn")
        should_crawl = bool(should_crawl_fn(product)) if should_crawl_fn is not None else False
        crawler_triggered = False
        if should_crawl and crawl_product_fn is not None:
            AnalysisWorkflow._mark_step(state, "crawling", 30)
            crawl_product_fn(db, product_id)
            crawler_triggered = True
            product = db.query(Product).filter(Product.id == product_id).first()
            if product is None:
                raise RuntimeError(f"Product disappeared after crawling: product_id={product_id}")

        comment_count = db.query(Comment).filter(Comment.product_id == product_id).count()
        vector_ready = False
        if comment_count > 0 and ensure_vector_ready_fn is not None:
            vector_ready = bool(ensure_vector_ready_fn(db, product_id))
        last_crawled_at = getattr(product, "last_crawled_at", None)
        if last_crawled_at is not None and getattr(last_crawled_at, "tzinfo", None) is None:
            last_crawled_at = last_crawled_at.replace(tzinfo=timezone.utc)
        data_issue = None
        if comment_count == 0:
            data_issue = "no_comments"
        elif not vector_ready:
            data_issue = "vector_not_ready"
        return {
            "data_context": DataContext(
                data_ready=comment_count > 0,
                used_cache=not crawler_triggered,
                crawler_triggered=crawler_triggered,
                vector_ready=vector_ready,
                last_crawled_at=last_crawled_at.isoformat() if last_crawled_at is not None else None,
                comment_count=comment_count,
                data_issue=data_issue,
            )
        }

    @staticmethod
    def _router_agent(state: MultiAgentAnalysisState) -> MultiAgentAnalysisState:
        """调用路由 Agent，决定是否启用 SQL、RAG、可视化能力。"""
        AnalysisWorkflow._mark_step(state, "router_agent", 45)
        product_context = state.get("product_context")
        decision = RouterAgent.route(
            question=state["user_message"],
            has_product=bool(product_context.has_product) if product_context is not None else False,
        )
        return {"route_decision": decision}

    @staticmethod
    def _dispatch_after_router(state: MultiAgentAnalysisState) -> str:
        """根据路由结果选择第一个需要执行的分析 Agent。"""
        route_decision = state["route_decision"]
        if route_decision.need_sql:
            return "sql_agent"
        if route_decision.need_rag:
            return "rag_agent"
        return "answer_agent"

    @staticmethod
    def _sql_agent(state: MultiAgentAnalysisState) -> MultiAgentAnalysisState:
        """执行结构化统计分析，并产出协议化 SQL 结果。"""
        AnalysisWorkflow._mark_step(state, "sql_agent", 60)
        product_context = state["product_context"]
        route_decision = state["route_decision"]
        result = SQLAgent.run(
            db=state["db"],
            product_id=product_context.product_id,
            question=state["user_message"],
            analysis_targets=route_decision.analysis_targets,
        )
        return {"sql_result": result}

    @staticmethod
    def _dispatch_after_sql(state: MultiAgentAnalysisState) -> str:
        """在 SQL 完成后，决定是否继续生成图表或检索评论证据。"""
        route_decision = state["route_decision"]
        if route_decision.need_visual:
            return "visual_agent"
        if route_decision.need_rag:
            return "rag_agent"
        return "answer_agent"

    @staticmethod
    def _visual_agent(state: MultiAgentAnalysisState) -> MultiAgentAnalysisState:
        """根据 SQL 指标生成图表 DSL。"""
        AnalysisWorkflow._mark_step(state, "visual_agent", 70)
        sql_result = state.get("sql_result")
        if sql_result is None:
            return {"visual_result": VisualAgentResult(charts=[])}

        if not VisualAgent.has_renderable_metrics(sql_result.metrics):
            return {"visual_result": VisualAgentResult(charts=[])}

        return {
            "visual_result": VisualAgent.run(
                question=state["user_message"],
                sql_result_metrics=sql_result.metrics,
            )
        }

    @staticmethod
    def _dispatch_after_visual(state: MultiAgentAnalysisState) -> str:
        """图表生成后，如果还需要评论语义分析则进入 RAG。"""
        return "rag_agent" if state["route_decision"].need_rag else "answer_agent"

    @staticmethod
    def _rag_agent(state: MultiAgentAnalysisState) -> MultiAgentAnalysisState:
        """执行评论证据检索与语义总结。"""
        AnalysisWorkflow._mark_step(state, "rag_agent", 80)
        product_context = state["product_context"]
        route_decision = state["route_decision"]
        result = RAGAgent.run(
            db=state["db"],
            product_id=product_context.product_id,
            question=state["user_message"],
            analysis_targets=route_decision.analysis_targets,
            route_reason=route_decision.reason,
            response_style=route_decision.response_style.value,
            sql_result_description=state.get("sql_result").description if state.get("sql_result") is not None else None,
        )
        return {"rag_result": result}

    @staticmethod
    def _answer_agent(state: MultiAgentAnalysisState) -> MultiAgentAnalysisState:
        """汇总多路结果，生成候选回答草稿。"""
        AnalysisWorkflow._mark_step(state, "answer_agent", 90)
        return {
            "answer_draft": AnswerAgent.run(
                question=state["user_message"],
                route_decision=state["route_decision"],
                sql_result=state.get("sql_result"),
                rag_result=state.get("rag_result"),
                visual_result=state.get("visual_result"),
            )
        }

    @staticmethod
    def _master_agent(state: MultiAgentAnalysisState) -> MultiAgentAnalysisState:
        """审查候选回答，并在必要时给出局部重试决策。"""
        AnalysisWorkflow._mark_step(state, "master_agent", 95)
        answer_draft = state.get("answer_draft")
        decision = MasterAgent.run(
            question=state["user_message"],
            route_decision=state["route_decision"],
            answer_text=answer_draft.answer if answer_draft is not None else "",
            answer_points=answer_draft.answer_points if answer_draft is not None else [],
            visual_result=state.get("visual_result"),
            retry_count=state.get("retry_count", 0),
            max_retry=state.get("max_retry", 1),
        )
        retry_count = state.get("retry_count", 0) + (1 if decision.decision.value == "retry" else 0)
        return {"master_decision": decision, "retry_count": retry_count}

    @staticmethod
    def _dispatch_after_master(state: MultiAgentAnalysisState) -> str:
        """按最终审查结果决定结束工作流还是局部重跑。"""
        decision = state["master_decision"]
        if decision.decision.value in {"pass", "fallback_pass"}:
            return "finalize"
        retry_from = decision.retry_from.value if decision.retry_from is not None else "answer_agent"
        if retry_from in {"sql_agent", "visual_agent", "rag_agent", "answer_agent"}:
            return retry_from
        return "answer_agent"

    @staticmethod
    def _finalize(state: MultiAgentAnalysisState) -> MultiAgentAnalysisState:
        """收敛最终输出，生成服务层可直接消费的最终协议结果。"""
        AnalysisWorkflow._mark_step(state, "finalize", 100, finished=True)
        answer_draft = state.get("answer_draft")
        visual_result = state.get("visual_result")
        product_context = state.get("product_context")
        return {
            "final_response": FinalAnalysisResponse(
                answer=answer_draft.answer if answer_draft is not None else "",
                charts=visual_result.charts if visual_result is not None else [],
                meta=FinalResponseMeta(
                    product_id=product_context.product_id if product_context is not None else None,
                    used_agents=[
                        "router_agent",
                        *(["sql_agent"] if state.get("sql_result") is not None else []),
                        *(["visual_agent"] if visual_result is not None and visual_result.charts else []),
                        *(["rag_agent"] if state.get("rag_result") is not None else []),
                        "answer_agent",
                        "master_agent",
                    ],
                    retry_count=state.get("retry_count", 0),
                ),
            )
        }

    @staticmethod
    def _mark_step(
        state: MultiAgentAnalysisState,
        current_step: str,
        progress: int,
        *,
        started: bool = False,
        finished: bool = False,
    ) -> None:
        """通过服务层回调同步任务状态，保持异步任务进度可观测。"""
        set_task_state_fn = state.get("set_task_state_fn")
        task = state.get("task")
        if set_task_state_fn is None or task is None or state.get("db") is None:
            return
        set_task_state_fn(
            state["db"],
            task,
            current_step=current_step,
            progress=progress,
            started=started,
            finished=finished,
        )
