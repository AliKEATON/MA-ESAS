"""Conversation-related Pydantic schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.analysis import AnalysisTaskStatus


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageType(str, Enum):
    CHAT = "chat"
    ANALYSIS_REQUEST = "analysis_request"
    ANALYSIS_RESULT = "analysis_result"
    SYSTEM_NOTICE = "system_notice"


class ConversationCreateRequest(BaseModel):
    bound_product_id: int | None = Field(default=None, description="Bound product id")

    class Config:
        json_schema_extra = {
            "example": {
                "bound_product_id": 1001,
            }
        }


class ConversationUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="Conversation title")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "京东商品差评分析",
            }
        }


class MessageSendRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000, description="Message content")

    class Config:
        json_schema_extra = {
            "example": {
                "content": "Why are there so many negative reviews for this product?",
            }
        }


class MessageResponse(BaseModel):
    id: int
    role: MessageRole
    message_type: MessageType
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class AnalysisTaskSummaryResponse(BaseModel):
    task_id: str
    status: AnalysisTaskStatus
    progress: int
    current_step: str | None
    product_id: int | None


class ConversationTaskResponse(BaseModel):
    task_id: str
    status: AnalysisTaskStatus
    progress: int
    current_step: str | None
    product_id: int | None
    question: str
    report_ready: bool
    created_at: datetime
    finished_at: datetime | None


class MessageSendResponse(BaseModel):
    user_message: MessageResponse
    analysis_task: AnalysisTaskSummaryResponse


class ConversationResponse(BaseModel):
    id: int
    title: str | None
    bound_product_id: int | None
    last_message_preview: str | None = None
    latest_task: AnalysisTaskSummaryResponse | None = None
    task_count: int = 0
    completed_task_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationDetailResponse(BaseModel):
    id: int
    title: str | None
    bound_product_id: int | None
    messages: list[MessageResponse]
    tasks: list[ConversationTaskResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ConversationResponse]
