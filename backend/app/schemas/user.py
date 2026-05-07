"""
用户相关 Pydantic Schema。
用于认证模块的请求与响应校验。
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """定义用户注册请求体。"""

    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=128, description="密码")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "testuser",
                "email": "user@example.com",
                "password": "password123",
            }
        }


class UserLoginRequest(BaseModel):
    """定义用户登录请求体。"""

    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "testuser",
                "password": "password123",
            }
        }


class UserChangePasswordRequest(BaseModel):
    """定义修改密码请求体。"""

    current_password: str = Field(..., min_length=6, max_length=128, description="当前密码")
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")

    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "password123",
                "new_password": "new-password-456",
            }
        }


class UserResponse(BaseModel):
    """定义用户信息响应体。"""

    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """定义登录令牌响应体。"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1440


class AuthResponse(BaseModel):
    """定义登录成功后的认证响应体。"""

    user: UserResponse
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1440


class PasswordChangeResponse(BaseModel):
    """定义修改密码成功响应体。"""

    success: bool = True
