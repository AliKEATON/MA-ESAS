"""
SQLAlchemy ORM 模型包
统一导出 Base 和所有 Model，供 Alembic 迁移和数据库初始化使用
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# 导入所有模型以确保 Alembic 能发现它们
from app.models.user import User
from app.models.product import Product
from app.models.comment import Comment
from app.models.conversation import Conversation, Message
from app.models.analysis_task import AnalysisTask
from app.models.analysis_report import AnalysisReport

__all__ = [
    "Base",
    "User",
    "Product",
    "Comment",
    "Conversation",
    "Message",
    "AnalysisTask",
    "AnalysisReport",
]
