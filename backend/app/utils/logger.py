"""
日志配置模块
使用 loguru 统一管理日志
"""

import sys
from loguru import logger
from app.config import LOG_LEVEL, LOG_FILE_PATH, LOG_MAX_SIZE, LOG_RETENTION_DAYS


def setup_logger():
    """
    初始化日志配置
    - 控制台输出：彩色、格式化
    - 文件输出：日志轮转、自动清理
    """
    
    # 移除默认 handler
    logger.remove()
    
    # 控制台输出配置
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        level=LOG_LEVEL,
        colorize=True,
    )
    
    # 文件输出配置
    logger.add(
        LOG_FILE_PATH,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} - "
            "{message}"
        ),
        level=LOG_LEVEL,
        rotation=LOG_MAX_SIZE,  # 日志轮转大小
        retention=f"{LOG_RETENTION_DAYS} days",  # 日志保留天数
        encoding="utf-8",
    )
    
    logger.info("日志系统初始化完成")
    return logger


# 初始化日志
setup_logger()
