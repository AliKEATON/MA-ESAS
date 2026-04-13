"""
数据库连接管理模块
管理 MySQL、DuckDB、ChromaDB 的连接
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
import duckdb
import chromadb
from app.utils.logger import logger
from app.config import (
    SQLALCHEMY_DATABASE_URL,
    DUCKDB_PATH,
    CHROMADB_PATH,
    SQL_ECHO,
)

# ========== MySQL 连接 ==========
# 创建 SQLAlchemy 引擎
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # 连接前检查连接是否有效
    echo=SQL_ECHO,  # 是否打印原始 SQL，默认关闭，必要时通过环境变量开启
)

# 创建 Session 工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """
    获取数据库会话
    用于 FastAPI 依赖注入
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ========== DuckDB 连接 ==========
def get_duckdb_connection():
    """
    获取 DuckDB 连接
    用于内存分析
    """
    try:
        conn = duckdb.connect(DUCKDB_PATH)
        logger.debug(f"DuckDB 连接成功: {DUCKDB_PATH}")
        return conn
    except Exception as e:
        logger.error(f"DuckDB 连接失败: {e}")
        raise


# ========== ChromaDB 连接 ==========
def get_chromadb_client():
    """
    获取 ChromaDB 客户端
    用于向量检索
    """
    try:
        client = chromadb.PersistentClient(path=CHROMADB_PATH)
        logger.debug(f"ChromaDB 连接成功: {CHROMADB_PATH}")
        return client
    except Exception as e:
        logger.error(f"ChromaDB 连接失败: {e}")
        raise


# ========== 数据库初始化 ==========
def init_databases():
    """
    初始化所有数据库
    - 创建 MySQL 表
    - 初始化 DuckDB
    - 初始化 ChromaDB
    """
    try:
        # MySQL 表初始化（通过 ORM 模型）
        from app.models import Base
        Base.metadata.create_all(bind=engine)
        logger.info("MySQL 表初始化完成")
        
        # DuckDB 初始化
        conn = get_duckdb_connection()
        conn.close()
        logger.info("DuckDB 初始化完成")
        
        # ChromaDB 初始化
        client = get_chromadb_client()
        logger.info("ChromaDB 初始化完成")
        
        logger.info("所有数据库初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise


# ========== 数据库健康检查 ==========
def check_database_health():
    """
    检查数据库连接状态
    """
    try:
        # 检查 MySQL
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        logger.info("✓ MySQL 连接正常")
    except Exception as e:
        logger.error(f"✗ MySQL 连接失败: {e}")
        raise
    
    try:
        # 检查 DuckDB
        conn = get_duckdb_connection()
        conn.execute("SELECT 1")
        conn.close()
        logger.info("✓ DuckDB 连接正常")
    except Exception as e:
        logger.error(f"✗ DuckDB 连接失败: {e}")
        raise
    
    try:
        # 检查 ChromaDB
        client = get_chromadb_client()
        logger.info("✓ ChromaDB 连接正常")
    except Exception as e:
        logger.error(f"✗ ChromaDB 连接失败: {e}")
        raise
