"""统一消息入口的会话服务。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AnalysisTask, Conversation, Message
from app.models.analysis_task import AnalysisTaskStatus
from app.models.conversation import MessageRole, MessageType
from app.schemas.conversation import (
    AnalysisTaskSummaryResponse,
    ConversationTaskResponse,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageHandlingMode,
    MessageResponse,
    MessageSendRequest,
    MessageSendResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.chat_service import ChatService
from app.utils.logger import logger


class ConversationService:
    """封装会话管理与消息分发逻辑。"""

    @staticmethod
    def _build_task_summary(task: AnalysisTask | None) -> AnalysisTaskSummaryResponse | None:
        """把分析任务模型转换为接口层需要的摘要结构。"""
        if task is None:
            return None
        return AnalysisTaskSummaryResponse(
            task_id=task.task_id,
            status=task.status,
            progress=task.progress,
            current_step=task.current_step,
            product_id=task.product_id,
        )

    @staticmethod
    def create_conversation(db: Session, user_id: int, req: ConversationCreateRequest) -> ConversationResponse:
        """为当前用户创建一个新会话。"""
        conversation = Conversation(
            user_id=user_id,
            bound_product_id=req.bound_product_id,
            title=None,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        logger.info(f"Conversation created: {conversation.id} for user {user_id}")
        return ConversationResponse.model_validate(conversation)

    @staticmethod
    def delete_conversation(db: Session, user_id: int, conversation_id: int) -> None:
        """删除当前用户指定的会话。"""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        db.delete(conversation)
        db.commit()
        logger.info(
            "Conversation deleted: conversation_id={} user_id={}",
            conversation_id,
            user_id,
        )

    @staticmethod
    def update_conversation(
        db: Session,
        user_id: int,
        conversation_id: int,
        req: ConversationUpdateRequest,
    ) -> ConversationResponse:
        """更新当前用户会话的标题。"""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        conversation.title = req.title.strip()
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(conversation)
        logger.info(
            "Conversation updated: conversation_id={} user_id={} title={}",
            conversation_id,
            user_id,
            conversation.title,
        )
        return ConversationResponse.model_validate(conversation)

    @staticmethod
    def get_conversation_list(
        db: Session,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> ConversationListResponse:
        """分页获取当前用户的会话列表及任务摘要。"""
        query = db.query(Conversation).filter(Conversation.user_id == user_id)
        total = query.count()
        conversations = query.order_by(Conversation.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        items: list[ConversationResponse] = []
        for item in conversations:
            last_message = db.query(Message).filter(
                Message.conversation_id == item.id
            ).order_by(Message.created_at.desc()).first()
            task_query = db.query(AnalysisTask).filter(
                AnalysisTask.conversation_id == item.id,
                AnalysisTask.user_id == user_id,
            )
            latest_task = task_query.order_by(AnalysisTask.created_at.desc()).first()
            task_count = task_query.count()
            completed_task_count = task_query.filter(
                AnalysisTask.status == AnalysisTaskStatus.COMPLETED
            ).count()
            items.append(
                ConversationResponse(
                    id=item.id,
                    title=item.title,
                    bound_product_id=item.bound_product_id,
                    last_message_preview=(last_message.content[:120] if last_message else None),
                    latest_task=ConversationService._build_task_summary(latest_task),
                    task_count=task_count,
                    completed_task_count=completed_task_count,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
            )
        logger.info(
            "Conversation list fetched: user_id={} total={} page={} page_size={}",
            user_id,
            total,
            page,
            page_size,
        )
        return ConversationListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
        )

    @staticmethod
    def get_conversation_detail(
        db: Session,
        user_id: int,
        conversation_id: int,
    ) -> ConversationDetailResponse:
        """获取单个会话的消息明细和关联任务。"""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        messages = db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.created_at.asc()).all()
        tasks = db.query(AnalysisTask).filter(
            AnalysisTask.conversation_id == conversation_id,
            AnalysisTask.user_id == user_id,
        ).order_by(AnalysisTask.created_at.desc()).all()
        logger.info(
            "Conversation detail fetched: conversation_id={} user_id={} message_count={} task_count={}",
            conversation_id,
            user_id,
            len(messages),
            len(tasks),
        )
        return ConversationDetailResponse(
            id=conversation.id,
            title=conversation.title,
            bound_product_id=conversation.bound_product_id,
            messages=[MessageResponse.model_validate(item) for item in messages],
            tasks=[
                ConversationTaskResponse(
                    task_id=item.task_id,
                    status=item.status,
                    progress=item.progress,
                    current_step=item.current_step,
                    product_id=item.product_id,
                    question=item.question,
                    report_ready=item.report is not None,
                    created_at=item.created_at,
                    finished_at=item.finished_at,
                )
                for item in tasks
            ],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    @staticmethod
    def get_conversation_tasks(
        db: Session,
        user_id: int,
        conversation_id: int,
    ) -> list[ConversationTaskResponse]:
        """获取指定会话下的分析任务列表。"""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        tasks = db.query(AnalysisTask).filter(
            AnalysisTask.conversation_id == conversation_id,
            AnalysisTask.user_id == user_id,
        ).order_by(AnalysisTask.created_at.desc()).all()
        logger.info(
            "Conversation tasks fetched: conversation_id={} user_id={} task_count={}",
            conversation_id,
            user_id,
            len(tasks),
        )
        return [
            ConversationTaskResponse(
                task_id=item.task_id,
                status=item.status,
                progress=item.progress,
                current_step=item.current_step,
                product_id=item.product_id,
                question=item.question,
                report_ready=item.report is not None,
                created_at=item.created_at,
                finished_at=item.finished_at,
            )
            for item in tasks
        ]

    @staticmethod
    def send_message(
        db: Session,
        user_id: int,
        conversation_id: int,
        req: MessageSendRequest,
    ) -> MessageSendResponse:
        """发送消息并按内容路由到普通聊天或分析任务流程。"""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        try:
            history_messages = list(reversed(
                db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(ChatService.MAX_HISTORY_MESSAGES)
                .all()
            ))
            product = AnalysisService.resolve_product_for_message(db, conversation, req.content)
            message_type = MessageType.ANALYSIS_REQUEST if product else MessageType.CHAT
            logger.info(
                "Message routing decided: conversation_id={} user_id={} message_type={} bound_product_id={} resolved_product_id={}",
                conversation_id,
                user_id,
                message_type.value,
                conversation.bound_product_id,
                product.id if product else None,
            )

            user_message = Message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                message_type=message_type,
                content=req.content,
            )
            db.add(user_message)
            db.flush()

            if not conversation.title:
                conversation.title = req.content[:50]
            conversation.updated_at = datetime.now(timezone.utc)

            if product is None:
                reply_content = ChatService.generate_reply(
                    conversation=conversation,
                    user_content=req.content,
                    history_messages=history_messages,
                )
                reply_message = Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    message_type=MessageType.CHAT,
                    content=reply_content,
                )
                db.add(reply_message)
                db.commit()
                db.refresh(user_message)
                db.refresh(reply_message)
                logger.info(f"Direct message saved: {user_message.id} in conversation {conversation_id}")
                logger.info(
                    "Direct reply generated: conversation_id={} user_message_id={} reply_message_id={}",
                    conversation_id,
                    user_message.id,
                    reply_message.id,
                )
                return MessageSendResponse(
                    handling_mode=MessageHandlingMode.DIRECT_REPLY,
                    user_message=MessageResponse.model_validate(user_message),
                    reply_message=MessageResponse.model_validate(reply_message),
                )

            reusable_task = AnalysisService.find_reusable_task(
                db=db,
                user_id=user_id,
                conversation_id=conversation_id,
                product_id=product.id,
                question=req.content,
            )
            if reusable_task is not None:
                task = reusable_task
                notice_content = (
                    "Existing analysis task reused. "
                    f"Use task_id={task.task_id} to query progress and result."
                )
                logger.info(
                    "Reusing analysis task instead of creating duplicate: task_id={} conversation_id={} user_message_id={}",
                    task.task_id,
                    conversation_id,
                    user_message.id,
                )
            else:
                task = AnalysisService.create_task_for_message(
                    db=db,
                    user_id=user_id,
                    conversation=conversation,
                    user_message=user_message,
                    product=product,
                    question=req.content,
                )
                notice_content = (
                    "Analysis task created. "
                    f"Use task_id={task.task_id} to query progress and result."
                )
            notice_message = Message(
                conversation_id=conversation_id,
                role=MessageRole.SYSTEM,
                message_type=MessageType.SYSTEM_NOTICE,
                content=notice_content,
            )
            db.add(notice_message)
            db.commit()
            db.refresh(user_message)
            db.refresh(task)
            db.refresh(notice_message)

            logger.info(
                "Task created from message: task_id={} conversation_id={} user_message_id={} notice_message_id={}",
                task.task_id,
                conversation_id,
                user_message.id,
                notice_message.id,
            )
            return MessageSendResponse(
                handling_mode=MessageHandlingMode.TASK_CREATED,
                user_message=MessageResponse.model_validate(user_message),
                reply_message=MessageResponse.model_validate(notice_message),
                analysis_task=AnalysisTaskSummaryResponse(
                    task_id=task.task_id,
                    status=task.status.value,
                    progress=task.progress,
                    current_step=task.current_step,
                    product_id=task.product_id,
                ),
            )
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_messages(
        db: Session,
        user_id: int,
        conversation_id: int,
    ) -> list[MessageResponse]:
        """获取指定会话的全部消息记录。"""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        messages = db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.created_at.asc()).all()
        logger.info(
            "Conversation messages fetched: conversation_id={} user_id={} message_count={}",
            conversation_id,
            user_id,
            len(messages),
        )
        return [MessageResponse.model_validate(item) for item in messages]
