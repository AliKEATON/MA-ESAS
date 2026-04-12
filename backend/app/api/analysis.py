"""
FastAPI 分析任务路由
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from loguru import logger

from app.api.auth import get_current_user_dependency
from app.db.database import get_db
from app.schemas.analysis import AnalysisTaskProgressResponse, AnalysisResultResponse
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/api/analysis/tasks", tags=["分析任务"])


@router.get("/{task_id}", response_model=ApiResponse[AnalysisTaskProgressResponse])
async def get_task_progress(
    task_id: str,
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db),
):
    """获取分析任务状态与进度。"""
    try:
        progress = AnalysisService.get_task_progress(db, current_user.id, task_id)
        return ApiResponse(
            code=200,
            data=AnalysisTaskProgressResponse.model_validate(progress),
            message="success",
        )
    except ValueError as e:
        logger.warning(f"Analysis task not found: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Get analysis task progress error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/{task_id}/result", response_model=ApiResponse[AnalysisResultResponse], status_code=200)
async def get_task_result(
    task_id: str,
    response: Response,
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db),
):
    """获取分析任务结果。"""
    try:
        result = AnalysisService.get_task_result(db, current_user.id, task_id)
        if result.get("status") == "failed":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error_message") or "Analysis failed",
            )
        if not result.get("result_ready"):
            response.status_code = status.HTTP_202_ACCEPTED
            return ApiResponse(
                code=202,
                data=None,
                message="Analysis result is not ready",
            )

        return ApiResponse(
            code=200,
            data=AnalysisResultResponse.model_validate(result),
            message="success",
        )
    except ValueError as e:
        logger.warning(f"Analysis task not found: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get analysis task result error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/{task_id}/retry", response_model=ApiResponse[AnalysisTaskProgressResponse], status_code=202)
async def retry_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db),
):
    """重试失败的分析任务。"""
    try:
        task = AnalysisService.retry_task(db, current_user.id, task_id)
        logger.info("Scheduling retried analysis task: task_id={}", task.task_id)
        background_tasks.add_task(AnalysisService.process_task, task.task_id)
        progress = AnalysisService.get_task_progress(db, current_user.id, task.task_id)
        return ApiResponse(
            code=202,
            data=AnalysisTaskProgressResponse.model_validate(progress),
            message="Analysis task retried",
        )
    except ValueError as e:
        logger.warning(f"Retry analysis task rejected: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Retry analysis task error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
