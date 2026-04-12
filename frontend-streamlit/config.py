"""
Streamlit 前端配置
"""

import os
from dotenv import load_dotenv

load_dotenv()

# 应用信息
APP_TITLE = "MA-ESAS 电商舆情分析"
APP_VERSION = "1.0.0"

# 后端 API 地址
FASTAPI_HOST = os.getenv("FASTAPI_HOST", "localhost")
FASTAPI_PORT = os.getenv("FASTAPI_PORT", "8000")
FASTAPI_BASE_URL = f"http://{FASTAPI_HOST}:{FASTAPI_PORT}"

# 支持的商品链接来源
ALLOWED_SOURCES = [
    "item.jd.com",
    "taobao.com",
    "detail.tmall.com",
]
