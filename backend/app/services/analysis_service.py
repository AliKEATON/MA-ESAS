"""Analysis service for task-backed product analysis."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agents.workflow import AnalysisWorkflow
from app.db.database import SessionLocal
from app.models import AnalysisReport, AnalysisTask, Comment, Conversation, Message, Product
from app.models.analysis_task import AnalysisTaskStatus
from app.models.conversation import MessageRole, MessageType
from app.models.product import ProductStatus
from app.schemas.agent_protocol import FinalAnalysisResponse
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

    @staticmethod
    def _dump_protocol_value(value: Any) -> Any:
        """把工作流中的协议对象转换为可安全落库的 JSON 结构。"""
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return value

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
        """统一更新分析任务状态，并把最新进度持久化到数据库。"""
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
        final_response = workflow_state.get("final_response")
        route_decision = workflow_state.get("route_decision")
        sql_result = workflow_state.get("sql_result")
        visual_result = workflow_state.get("visual_result")
        rag_result = workflow_state.get("rag_result")
        answer_draft = workflow_state.get("answer_draft")
        master_decision = workflow_state.get("master_decision")
        retry_count = workflow_state.get("retry_count", 0)

        summary = final_response.answer if isinstance(final_response, FinalAnalysisResponse) else None
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
            "final_response": final_response.model_dump() if isinstance(final_response, FinalAnalysisResponse) else None,
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
            (final_response.meta.used_agents if isinstance(final_response, FinalAnalysisResponse) else []),
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
            workflow_state = AnalysisWorkflow.run(
                {
                    "db": db,
                    "task": task,
                    "task_id": task.task_id,
                    "user_id": task.user_id,
                    "conversation_id": task.conversation_id,
                    "user_message": task.question,
                    "error_message": None,
                    "set_task_state_fn": AnalysisService._set_task_state,
                    "should_crawl_fn": AnalysisService._should_crawl,
                    "crawl_product_fn": CrawlerService.crawl_product,
                    "ensure_vector_ready_fn": AnalysisService._ensure_vector_ready,
                    "product_resolved_from": AnalysisService._infer_product_resolved_from(task),
                }
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
        """返回任务当前进度，并把数据库状态映射为前端可展示的步骤列表。"""
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
        """返回任务最终结果；若结果尚未就绪，则返回当前任务状态。"""
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
