"""
FastAPI 应用入口
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import FASTAPI_TITLE, FASTAPI_VERSION, FASTAPI_DESCRIPTION, ENVIRONMENT
from app.db.database import init_databases


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动事件
    logger.info("MA-ESAS 后端服务启动中...")
    init_databases()
    logger.info("MA-ESAS 后端服务启动完成")
    yield
    # 关闭事件
    logger.info("MA-ESAS 后端服务关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=FASTAPI_TITLE,
    version=FASTAPI_VERSION,
    description=FASTAPI_DESCRIPTION,
    docs_url="/docs" if ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if ENVIRONMENT == "development" else None,
    lifespan=lifespan,
)
# 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],  # Streamlit 前端地址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "version": FASTAPI_VERSION}


# 注册路由
from app.api import auth, conversations, analysis
app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(analysis.router)
