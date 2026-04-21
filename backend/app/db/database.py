"""
数据库连接管理模块
管理 MySQL、DuckDB、ChromaDB 的连接
"""

import tempfile
from pathlib import Path

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


_chromadb_client = None
_chromadb_client_path = None

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
    配置目录不可用时自动切换到 ASCII 安全路径
    """
    global _chromadb_client, _chromadb_client_path

    if _chromadb_client is not None:
        return _chromadb_client

    errors: list[str] = []
    for index, candidate_path in enumerate(_build_chromadb_candidate_paths()):
        try:
            path_obj = Path(candidate_path)
            path_obj.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(path_obj))
            _chromadb_client = client
            _chromadb_client_path = str(path_obj)

            if index == 0:
                logger.debug("ChromaDB client initialized: path={}", path_obj)
            else:
                logger.warning(
                    "ChromaDB fallback path enabled: configured_path={} active_path={}",
                    CHROMADB_PATH,
                    path_obj,
                )
            return client
        except Exception as exc:
            errors.append(f"{candidate_path}: {exc}")
            logger.warning(
                "ChromaDB client initialization failed: path={} error={}",
                candidate_path,
                exc,
            )

    raise RuntimeError("Failed to initialize ChromaDB client. " + " | ".join(errors))


def get_chromadb_client_path() -> str | None:
    """
    返回当前生效的 ChromaDB 目录
    便于日志和测试确认
    """
    return _chromadb_client_path


def _build_chromadb_candidate_paths() -> list[str]:
    """
    构造 ChromaDB 候选目录
    先尝试项目配置目录，再退回系统临时目录
    """
    configured_path = Path(CHROMADB_PATH).resolve()
    safe_path = Path(tempfile.gettempdir()) / "ma_esas_chromadb" / "persistent"

    candidates = [str(configured_path)]
    safe_path_str = str(safe_path.resolve())
    if safe_path_str not in candidates:
        candidates.append(safe_path_str)
    return candidates


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
