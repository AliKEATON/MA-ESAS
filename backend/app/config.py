"""
后端配置管理模块
集中管理所有配置：数据库、API、日志等
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ========== 项目路径 ==========
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

# 优先从项目根目录加载 .env，避免启动目录变化导致配置漂移
load_dotenv(BASE_DIR / ".env")


def _resolve_storage_path(path_value: str, default_path: Path) -> str:
    """将配置中的存储路径解析为基于项目根目录的绝对路径。"""
    raw_value = (path_value or "").strip()
    if not raw_value:
        return str(default_path)

    candidate = Path(raw_value)
    if candidate.is_absolute():
        return str(candidate)
    return str((BASE_DIR / candidate).resolve())

# 确保目录存在
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / "duckdb").mkdir(exist_ok=True)
(DATA_DIR / "chromadb").mkdir(exist_ok=True)

# ========== 环境配置 ==========
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# ========== FastAPI 配置 ==========
FASTAPI_HOST = os.getenv("FASTAPI_HOST", "0.0.0.0")
FASTAPI_PORT = int(os.getenv("FASTAPI_PORT", 8000))
FASTAPI_TITLE = "MA-ESAS API"
FASTAPI_VERSION = "1.0.0"
FASTAPI_DESCRIPTION = "基于多智能体协同的电商商品舆情分析系统"

# ========== 数据库配置 ==========
# MySQL
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "ma_esas")

# SQLAlchemy 数据库 URL
SQLALCHEMY_DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@"
    f"{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)

# DuckDB
DUCKDB_PATH = _resolve_storage_path(
    os.getenv("DUCKDB_PATH", ""),
    DATA_DIR / "duckdb" / "analysis.duckdb",
)

# ChromaDB
CHROMADB_PATH = _resolve_storage_path(
    os.getenv("CHROMADB_PATH", ""),
    DATA_DIR / "chromadb",
)

# ========== AI 模型配置 ==========
# DeepSeek API
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Embedding 模型
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", DEEPSEEK_API_KEY)
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", DEEPSEEK_API_BASE)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# ========== 爬虫配置 ==========
JD_CRAWLER_TIMEOUT = int(os.getenv("JD_CRAWLER_TIMEOUT", 30))
JD_CRAWLER_RETRY_TIMES = int(os.getenv("JD_CRAWLER_RETRY_TIMES", 3))
JD_CRAWLER_RETRY_DELAY = int(os.getenv("JD_CRAWLER_RETRY_DELAY", 5))
JD_CRAWLER_USER_AGENT = os.getenv(
    "JD_CRAWLER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
)
JD_CRAWLER_BROWSER_PATH = os.getenv("JD_CRAWLER_BROWSER_PATH", "").strip()
JD_CRAWLER_USE_SYSTEM_USER_PATH = os.getenv("JD_CRAWLER_USE_SYSTEM_USER_PATH", "False").lower() == "true"
JD_CRAWLER_USER_DATA_PATH = os.getenv("JD_CRAWLER_USER_DATA_PATH", "").strip()
JD_CRAWLER_PROFILE = os.getenv("JD_CRAWLER_PROFILE", "Default").strip() or "Default"
JD_CRAWLER_LOCAL_PORT = int(os.getenv("JD_CRAWLER_LOCAL_PORT", "0") or 0)

# ========== 邮件配置 ==========
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")

# ========== 认证配置 ==========
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", 1440))

# ========== 日志配置 ==========
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE_PATH = _resolve_storage_path(
    os.getenv("LOG_FILE_PATH", ""),
    LOGS_DIR / "app.log",
)
LOG_MAX_SIZE = os.getenv("LOG_MAX_SIZE", "500MB")
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", 7))
SQL_ECHO = os.getenv("SQL_ECHO", "False").lower() == "true"

# ========== 系统配置 ==========
# 允许的商品链接来源
ALLOWED_SOURCES = ["jd.com", "taobao.com", "tmall.com"]

# 分析超时时间（秒）
ANALYSIS_TIMEOUT = 300

# 最大并发爬虫数
MAX_CONCURRENT_CRAWLERS = 3
