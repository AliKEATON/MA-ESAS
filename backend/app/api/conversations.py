"""
FastAPI 对话路由
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_dependency
from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.conversation import (
    ConversationTaskResponse,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdateRequest,
    MessageResponse,
    MessageSendRequest,
    MessageSendResponse,
)
from app.schemas.user import UserResponse
from app.services.analysis_service import AnalysisService
from app.services.conversation_service import ConversationService
from app.utils.logger import logger

router = APIRouter(prefix="/api/conversations", tags=["对话"])


@router.post("", response_model=ApiResponse[ConversationResponse], status_code=201)
async def create_conversation(
    req: ConversationCreateRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """创建对话"""
    try:
        conversation = ConversationService.create_conversation(db, current_user.id, req)
        return ApiResponse(
            code=201,
            data=conversation,
            message="Conversation created successfully"
        )
    except Exception as e:
        logger.error("创建会话失败：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("", response_model=ApiResponse[ConversationListResponse])
async def get_conversation_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """获取对话列表"""
    try:
        result = ConversationService.get_conversation_list(db, current_user.id, page, page_size)
        return ApiResponse(
            code=200,
            data=result,
            message="success"
        )
    except Exception as e:
        logger.error("获取会话列表失败：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/{conversation_id}", response_model=ApiResponse[ConversationDetailResponse])
async def get_conversation_detail(
    conversation_id: int,
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """获取对话详情"""
    try:
        detail = ConversationService.get_conversation_detail(db, current_user.id, conversation_id)
        return ApiResponse(
            code=200,
            data=detail,
            message="success"
        )
    except ValueError as e:
        logger.warning("会话不存在：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("获取会话详情失败：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/{conversation_id}/messages", response_model=ApiResponse[MessageSendResponse], status_code=202)
async def send_message(
    conversation_id: int,
    req: MessageSendRequest,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """发送消息并统一创建分析任务。"""
    try:
        result = ConversationService.send_message(db, current_user.id, conversation_id, req)
        logger.info(
            "准备调度后台分析任务：conversation_id={} task_id={}",
            conversation_id,
            result.analysis_task.task_id,
        )
        background_tasks.add_task(AnalysisService.process_task, result.analysis_task.task_id)
        return ApiResponse(
            code=202,
            data=result,
            message="Analysis task created"
        )
    except ValueError as e:
        logger.warning("会话无效：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("发送消息失败：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/{conversation_id}/messages", response_model=ApiResponse[list[MessageResponse]])
async def get_messages(
    conversation_id: int,
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """获取对话的所有消息"""
    try:
        messages = ConversationService.get_messages(db, current_user.id, conversation_id)
        return ApiResponse(
            code=200,
            data=messages,
            message="success"
        )
    except ValueError as e:
        logger.warning("获取消息被拒绝：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("获取消息失败：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.delete("/{conversation_id}", response_model=ApiResponse[dict[str, int]])
async def delete_conversation(
    conversation_id: int,
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """删除当前用户的会话。"""
    try:
        ConversationService.delete_conversation(db, current_user.id, conversation_id)
        return ApiResponse(
            code=200,
            data={"conversation_id": conversation_id},
            message="Conversation deleted successfully"
        )
    except ValueError as e:
        logger.warning("删除会话被拒绝：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("删除会话失败：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.patch("/{conversation_id}", response_model=ApiResponse[ConversationResponse])
async def update_conversation(
    conversation_id: int,
    req: ConversationUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """更新当前用户的会话标题。"""
    try:
        conversation = ConversationService.update_conversation(db, current_user.id, conversation_id, req)
        return ApiResponse(
            code=200,
            data=conversation,
            message="Conversation updated successfully"
        )
    except ValueError as e:
        logger.warning("更新会话被拒绝：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("更新会话失败：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/{conversation_id}/tasks", response_model=ApiResponse[list[ConversationTaskResponse]])
async def get_conversation_tasks(
    conversation_id: int,
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """获取会话关联的分析任务列表。"""
    try:
        tasks = ConversationService.get_conversation_tasks(db, current_user.id, conversation_id)
        return ApiResponse(
            code=200,
            data=tasks,
            message="success"
        )
    except ValueError as e:
        logger.warning("获取会话任务列表失败：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error("获取会话任务列表异常：{}", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
