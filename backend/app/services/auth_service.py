"""
认证服务。
处理用户注册、登录、令牌校验和密码修改等业务逻辑。
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET_KEY
from app.models import User
from app.schemas.user import UserLoginRequest, UserRegisterRequest
from app.utils.logger import logger

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """封装认证模块的核心业务逻辑。"""

    @staticmethod
    def hash_password(password: str) -> str:
        """对明文密码进行哈希。"""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """校验明文密码与哈希密码是否匹配。"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def create_access_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
        """为指定用户生成访问令牌。"""
        if expires_delta is None:
            expires_delta = timedelta(minutes=JWT_EXPIRE_MINUTES)

        expire = datetime.now(timezone.utc) + expires_delta
        to_encode = {"sub": str(user_id), "exp": expire}
        return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    @staticmethod
    def verify_token(token: str) -> Optional[int]:
        """校验访问令牌并返回用户 ID。"""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("sub")
            if user_id is None:
                return None
            return int(user_id)
        except JWTError:
            logger.warning("令牌校验失败")
            return None

    @staticmethod
    def register(db: Session, req: UserRegisterRequest) -> User:
        """创建新用户并写入数据库。"""
        existing_user = db.query(User).filter(User.username == req.username).first()
        if existing_user:
            raise ValueError(f"用户名 {req.username} 已存在")

        existing_email = db.query(User).filter(User.email == req.email).first()
        if existing_email:
            raise ValueError(f"邮箱 {req.email} 已被注册")

        user = User(
            username=req.username,
            email=req.email,
            hashed_password=AuthService.hash_password(req.password),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        logger.info("用户注册成功：username={}", user.username)
        return user

    @staticmethod
    def login(db: Session, req: UserLoginRequest) -> Optional[User]:
        """校验登录信息并返回用户实体。"""
        user = db.query(User).filter(User.username == req.username).first()

        if not user:
            logger.warning("登录失败：用户不存在，username={}", req.username)
            return None

        if not user.is_active:
            logger.warning("登录失败：用户已停用，username={}", user.username)
            return None

        if not AuthService.verify_password(req.password, user.hashed_password):
            logger.warning("登录失败：密码错误，username={}", req.username)
            return None

        logger.info("用户登录成功：username={}", user.username)
        return user

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        """根据用户 ID 查询用户。"""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def change_password(db: Session, user_id: int, current_password: str, new_password: str) -> User:
        """校验旧密码后更新用户密码。"""
        user = AuthService.get_user_by_id(db, user_id)
        if not user:
            raise ValueError("用户不存在")

        if not user.is_active:
            raise ValueError("当前用户已被停用，无法修改密码")

        if not AuthService.verify_password(current_password, user.hashed_password):
            raise ValueError("当前密码错误")

        if current_password == new_password:
            raise ValueError("新密码不能与当前密码相同")

        user.hashed_password = AuthService.hash_password(new_password)
        db.add(user)
        db.commit()
        db.refresh(user)

        logger.info("用户修改密码成功：user_id={} username={}", user.id, user.username)
        return user
