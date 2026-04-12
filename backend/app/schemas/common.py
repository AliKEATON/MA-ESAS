"""
通用响应 Schema
"""

from pydantic import BaseModel
from typing import Optional, Any, Generic, TypeVar

T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式"""
    code: int
    data: Optional[T] = None
    message: str = "success"

    # 配置 Pydantic 模型的额外行为，如定义文档示例等
    class Config:
        json_schema_extra = {
            "example": {
                "code": 200,
                "data": {},
                "message": "success"
            }
        }


class ErrorResponse(BaseModel):
    """错误响应"""
    code: int
    data: None = None
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "code": 400,
                "data": None,
                "message": "商品链接格式不支持"
            }
        }
