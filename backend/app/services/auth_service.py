"""
认证服务
处理用户注册、登录、密码验证等业务逻辑
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from loguru import logger

from app.config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRE_MINUTES
from app.models import User
from app.schemas.user import UserRegisterRequest, UserLoginRequest, UserResponse

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """认证服务"""

    @staticmethod
    def hash_password(password: str) -> str:
        """密码加密"""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def create_access_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
        """生成 JWT Token"""
        if expires_delta is None:
            expires_delta = timedelta(minutes=JWT_EXPIRE_MINUTES)
        
        expire = datetime.now(timezone.utc) + expires_delta
        to_encode = {"sub": str(user_id), "exp": expire}
        
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return encoded_jwt

    @staticmethod
    def verify_token(token: str) -> Optional[int]:
        """验证 Token，返回 user_id"""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id is None:
                return None
            return int(user_id)
        except JWTError:
            logger.warning(f"Invalid token: {token}")
            return None

    @staticmethod
    def register(db: Session, req: UserRegisterRequest) -> User:
        """用户注册"""
        # 检查用户名是否已存在
        existing_user = db.query(User).filter(User.username == req.username).first()
        if existing_user:
            raise ValueError(f"用户名 {req.username} 已存在")
        
        # 检查邮箱是否已存在
        existing_email = db.query(User).filter(User.email == req.email).first()
        if existing_email:
            raise ValueError(f"邮箱 {req.email} 已被注册")
        
        # 创建新用户
        user = User(
            username=req.username,
            email=req.email,
            hashed_password=AuthService.hash_password(req.password),
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        logger.info(f"User registered: {user.username}")
        return user

    @staticmethod
    def login(db: Session, req: UserLoginRequest) -> Optional[User]:
        """用户登录"""
        user = db.query(User).filter(User.username == req.username).first()
        
        if not user:
            logger.warning(f"Login failed: user {req.username} not found")
            return None
        
        if not user.is_active:
            logger.warning(f"Login failed: user {user.username} is inactive")
            return None
        
        if not AuthService.verify_password(req.password, user.hashed_password):
            logger.warning(f"Login failed: invalid password for {req.username}")
            return None
        
        logger.info(f"User logged in: {user.username}")
        return user

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        """根据 ID 获取用户"""
        return db.query(User).filter(User.id == user_id).first()
