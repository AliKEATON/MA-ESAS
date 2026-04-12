"""
用户相关 Pydantic Schema
用于 API 请求/响应数据验证
"""

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


# ========== 请求 Schema ==========

class UserRegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=128, description="密码")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "testuser",
                "email": "user@example.com",
                "password": "password123"
            }
        }


class UserLoginRequest(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "testuser",
                "password": "password123"
            }
        }


# ========== 响应 Schema ==========

class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """登录 Token 响应"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1440  # 分钟


class AuthResponse(BaseModel):
    """认证响应（包含用户信息和 Token）"""
    user: UserResponse
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1440
