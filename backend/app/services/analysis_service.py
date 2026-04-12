"""Analysis service for task-backed product analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from loguru import logger
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models import AnalysisReport, AnalysisTask, Conversation, Message, Product
from app.models.analysis_task import AnalysisTaskStatus
from app.models.conversation import MessageRole, MessageType
from app.models.product import ProductStatus
from app.services.crawler_service import CrawlerService
from app.utils.link_extractor import LinkExtractor


class AnalysisService:
    """Service helpers for product-analysis task creation and querying."""

    STEP_FLOW = [
        ("link_extract", "Link extraction"),
        ("crawl_check", "Crawl freshness check"),
        ("crawling", "Crawler collection"),
        ("sql_agent", "SQL aggregation"),
        ("rag_agent", "Semantic retrieval"),
        ("synthesizer", "Result synthesis"),
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
        lowered = text.lower()
        return any(keyword in lowered for keyword in AnalysisService.ANALYSIS_KEYWORDS)

    @staticmethod
    def _get_or_create_product(db: Session, link_info: dict[str, str]) -> Product:
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
        """Resolve the product to analyze for a message, if any."""
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
    def create_task_for_message(
        db: Session,
        user_id: int,
        conversation: Conversation,
        user_message: Message,
        product: Product,
        question: str,
    ) -> AnalysisTask:
        """Persist an analysis task for a previously saved user message."""
        conversation.bound_product_id = product.id
        task = AnalysisTask(
            task_id=str(uuid.uuid4()),
            user_id=user_id,
            conversation_id=conversation.id,
            product_id=product.id,
            trigger_message_id=user_message.id,
            question=question,
            status=AnalysisTaskStatus.PENDING,
            current_step="crawl_check",
            progress=10,
        )
        db.add(task)
        db.flush()
        logger.info(
            "Analysis task created: task_id={} conversation_id={} product_id={} trigger_message_id={}",
            task.task_id,
            conversation.id,
            product.id,
            user_message.id,
        )
        return task

    @staticmethod
    def _build_summary(product: Product, stats: dict[str, Any], evidence_count: int) -> str:
        total_count = stats.get("total_count", 0)
        avg_score = stats.get("avg_score", 0)
        if total_count <= 0:
            return (
                f"Product {product.external_product_id} currently has no captured comments. "
                "The task completed, but there is not enough review data to generate deeper insights yet."
            )
        return (
            f"Product {product.external_product_id} has {total_count} captured comments with an average score of "
            f"{avg_score}. The basic report includes score distribution and {evidence_count} evidence comments."
        )

    @staticmethod
    def _build_chart_config(stats: dict[str, Any]) -> dict[str, Any]:
        score_distribution = stats.get("score_distribution", {}) or {}
        labels = [str(key) for key in sorted(score_distribution.keys())]
        values = [score_distribution[int(key)] if isinstance(next(iter(score_distribution.keys()), None), int) else score_distribution[key] for key in labels]
        return {
            "score_distribution": {
                "xAxis": labels,
                "series": values,
            },
            "dimension_stats": stats.get("dimension_stats", {}) or {},
        }

    @staticmethod
    def _build_evidence(comments: list[Any]) -> list[dict[str, Any]]:
        evidence_items: list[dict[str, Any]] = []
        for comment in comments:
            evidence_items.append(
                {
                    "content": comment.content,
                    "score": comment.score,
                    "dimension": comment.dimension,
                    "similarity": None,
                }
            )
        return evidence_items

    @staticmethod
    def _build_result_message_content(task: AnalysisTask, report: AnalysisReport) -> str:
        product = task.product
        stats = report.statistics_json or {}
        total_count = stats.get("total_count", 0)
        avg_score = stats.get("avg_score", 0)
        return (
            f"Analysis completed for product {product.external_product_id}.\n"
            f"Task ID: {task.task_id}\n"
            f"Report ID: {report.id}\n"
            f"Total comments: {total_count}\n"
            f"Average score: {avg_score}\n"
            f"Summary: {report.summary or 'No summary generated.'}"
        )

    @staticmethod
    def _upsert_result_message(db: Session, task: AnalysisTask, report: AnalysisReport) -> Message | None:
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
    def _upsert_basic_report(db: Session, task: AnalysisTask) -> AnalysisReport:
        product = task.product
        stats = CrawlerService.get_comment_statistics(db, product.id)
        comments = CrawlerService.get_product_comments(db, product.id, limit=5)
        summary = AnalysisService._build_summary(product, stats, len(comments))
        charts_config = AnalysisService._build_chart_config(stats)
        evidence_json = AnalysisService._build_evidence(comments)

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
        report.statistics_json = stats
        report.charts_config = charts_config
        report.evidence_json = evidence_json
        db.commit()
        db.refresh(report)
        logger.info(
            "Analysis report saved: task_id={} report_id={} total_comments={}",
            task.task_id,
            report.id,
            stats.get("total_count", 0),
        )
        AnalysisService._upsert_result_message(db, task, report)
        return report

    @staticmethod
    def process_task(task_id: str) -> None:
        """Run a basic end-to-end task flow in the background."""
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
            AnalysisService._set_task_state(
                db,
                task,
                status=AnalysisTaskStatus.PROCESSING,
                current_step="link_extract",
                progress=5,
                started=True,
            )
            AnalysisService._set_task_state(db, task, current_step="crawl_check", progress=15)

            product = task.product
            should_crawl = AnalysisService._should_crawl(product)
            logger.info(
                "Task crawl decision: task_id={} product_id={} should_crawl={} last_crawled_at={}",
                task.task_id,
                product.id,
                should_crawl,
                product.last_crawled_at,
            )
            if should_crawl:
                AnalysisService._set_task_state(db, task, current_step="crawling", progress=30)
                CrawlerService.crawl_product(db, product.id)
            else:
                logger.info(
                    "Skip crawling for task_id={} because product data is fresh",
                    task.task_id,
                )

            AnalysisService._set_task_state(db, task, current_step="sql_agent", progress=60)
            stats = CrawlerService.get_comment_statistics(db, product.id)
            logger.info(
                "Statistics prepared for task_id={} total_count={} avg_score={}",
                task.task_id,
                stats.get("total_count"),
                stats.get("avg_score"),
            )
            AnalysisService._set_task_state(db, task, current_step="rag_agent", progress=80)
            AnalysisService._set_task_state(db, task, current_step="synthesizer", progress=90)
            AnalysisService._upsert_basic_report(db, task)
            AnalysisService._set_task_state(
                db,
                task,
                status=AnalysisTaskStatus.COMPLETED,
                current_step="synthesizer",
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
                        current_step=task.current_step or "crawl_check",
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
    def start_analysis(
        db: Session,
        user_id: int,
        conversation_id: int,
        question: str,
        product_url: str | None = None,
    ) -> dict[str, Any]:
        """Compatibility entrypoint that now persists an analysis task."""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        content = question if not product_url else f"{question}\n{product_url}"
        product = AnalysisService.resolve_product_for_message(db, conversation, content)
        if product is None:
            raise ValueError("No supported product link found in message content")

        user_message = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            message_type=MessageType.ANALYSIS_REQUEST,
            content=question,
        )
        db.add(user_message)
        db.flush()

        task = AnalysisService.create_task_for_message(
            db=db,
            user_id=user_id,
            conversation=conversation,
            user_message=user_message,
            product=product,
            question=question,
        )
        db.commit()
        db.refresh(task)
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "progress": task.progress,
            "current_step": task.current_step,
            "product_id": task.product_id,
        }

    @staticmethod
    def _should_crawl(product: Product) -> bool:
        if product.last_crawled_at is None:
            return True
        now = datetime.now(timezone.utc)
        return (now - product.last_crawled_at).days > 3

    @staticmethod
    def get_task_by_task_id(db: Session, user_id: int, task_id: str) -> AnalysisTask:
        task = db.query(AnalysisTask).filter(
            AnalysisTask.task_id == task_id,
            AnalysisTask.user_id == user_id,
        ).first()
        if not task:
            raise ValueError(f"Analysis task not found: {task_id}")
        return task

    @staticmethod
    def retry_task(db: Session, user_id: int, task_id: str) -> AnalysisTask:
        task = AnalysisService.get_task_by_task_id(db, user_id, task_id)
        if task.status != AnalysisTaskStatus.FAILED:
            raise ValueError(f"Only failed tasks can be retried: {task_id}")

        task.status = AnalysisTaskStatus.PENDING
        task.current_step = "crawl_check"
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
            "product": {
                "product_id": product.id,
                "source": product.source,
                "external_product_id": product.external_product_id,
                "product_name": product.product_name,
            },
            "summary": report.summary,
            "statistics": report.statistics_json,
            "evidence": evidence_items,
            "charts_config": report.charts_config,
            "created_at": report.created_at,
            "result_ready": True,
        }
