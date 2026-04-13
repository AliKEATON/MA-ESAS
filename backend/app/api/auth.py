"""
FastAPI 认证路由
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from loguru import logger

from app.db.database import get_db
from app.schemas.user import (
    UserRegisterRequest, UserLoginRequest, UserResponse, TokenResponse, AuthResponse
)
from app.schemas.common import ApiResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["认证"])


def get_current_user(token: str = None, db: Session = Depends(get_db)) -> UserResponse:
    """获取当前用户（依赖注入）"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token"
        )
    
    # 从 "Bearer <token>" 中提取 token
    if token.startswith("Bearer "):
        token = token[7:]
    
    user_id = AuthService.verify_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    user = AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse.model_validate(user)


def get_current_user_dependency(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> UserResponse:
    """从 Authorization Header 中解析当前用户。"""
    return get_current_user(authorization, db)


@router.post("/register", response_model=ApiResponse[UserResponse])
async def register(req: UserRegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    try:
        user = AuthService.register(db, req)
        return ApiResponse(
            code=201,
            data=UserResponse.model_validate(user),
            message="User registered successfully"
        )
    except ValueError as e:
        logger.warning(f"Registration failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/login", response_model=ApiResponse[AuthResponse])
async def login(req: UserLoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    try:
        user = AuthService.login(db, req)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        
        access_token = AuthService.create_access_token(user.id)
        
        return ApiResponse(
            code=200,
            data=AuthResponse(
                user=UserResponse.model_validate(user),
                access_token=access_token,
                token_type="bearer",
                expires_in=1440
            ),
            message="Login successful"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/me", response_model=ApiResponse[UserResponse])
async def get_current_user_info(
    current_user: UserResponse = Depends(get_current_user_dependency),
):
    """获取当前用户信息"""
    try:
        return ApiResponse(
            code=200,
            data=current_user,
            message="success"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user info error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
