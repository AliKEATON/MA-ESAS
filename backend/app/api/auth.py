"""
FastAPI 认证路由。
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.user import (
    AuthResponse,
    PasswordChangeResponse,
    UserChangePasswordRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.utils.logger import logger

router = APIRouter(prefix="/api/auth", tags=["认证"])


def get_current_user(token: str | None = None, db: Session = Depends(get_db)) -> UserResponse:
    """解析访问令牌并返回当前用户。"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )

    if token.startswith("Bearer "):
        token = token[7:]

    user_id = AuthService.verify_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse.model_validate(user)


def get_current_user_dependency(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> UserResponse:
    """从 Authorization 请求头中解析当前用户。"""
    return get_current_user(authorization, db)


@router.post("/register", response_model=ApiResponse[UserResponse])
async def register(req: UserRegisterRequest, db: Session = Depends(get_db)):
    """处理用户注册请求。"""
    try:
        user = AuthService.register(db, req)
        return ApiResponse(
            code=201,
            data=UserResponse.model_validate(user),
            message="User registered successfully",
        )
    except ValueError as exc:
        logger.warning("用户注册失败：{}", str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("用户注册发生异常：{}", str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/login", response_model=ApiResponse[AuthResponse])
async def login(req: UserLoginRequest, db: Session = Depends(get_db)):
    """处理用户登录请求。"""
    try:
        user = AuthService.login(db, req)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        access_token = AuthService.create_access_token(user.id)
        return ApiResponse(
            code=200,
            data=AuthResponse(
                user=UserResponse.model_validate(user),
                access_token=access_token,
                token_type="bearer",
                expires_in=1440,
            ),
            message="Login successful",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("用户登录发生异常：{}", str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/me", response_model=ApiResponse[UserResponse])
async def get_current_user_info(current_user: UserResponse = Depends(get_current_user_dependency)):
    """返回当前登录用户信息。"""
    try:
        return ApiResponse(code=200, data=current_user, message="success")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("获取当前用户信息失败：{}", str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post("/change-password", response_model=ApiResponse[PasswordChangeResponse])
async def change_password(
    req: UserChangePasswordRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    db: Session = Depends(get_db),
):
    """校验旧密码后修改当前用户密码。"""
    try:
        AuthService.change_password(
            db=db,
            user_id=current_user.id,
            current_password=req.current_password,
            new_password=req.new_password,
        )
        return ApiResponse(
            code=200,
            data=PasswordChangeResponse(success=True),
            message="Password updated successfully",
        )
    except ValueError as exc:
        logger.warning("修改密码失败：user_id={} reason={}", current_user.id, str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("修改密码发生异常：user_id={} error={}", current_user.id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
