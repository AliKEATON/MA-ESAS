'''
"""
前端 API 调用客户端
封装对 FastAPI 后端的所有 HTTP 请求
"""

import requests
from frontend.config import FASTAPI_BASE_URL


class APIClient:
    """FastAPI 后端客户端"""

    def __init__(self, token: str = None):
        self.base_url = FASTAPI_BASE_URL
        self.token = token
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def health_check(self) -> dict:
        """检查后端服务是否正常"""
        resp = requests.get(f"{self.base_url}/health", timeout=5)
        resp.raise_for_status()
        return resp.json()
'''

from utils.api_client_v2 import APIClient, APIClientError
'''

    # ========== 认证 ==========
    def login(self, username: str, password: str) -> dict:
        """用户登录"""
        resp = requests.post(
            f"{self.base_url}/api/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def register(self, username: str, password: str, email: str) -> dict:
        """用户注册"""
        resp = requests.post(
            f"{self.base_url}/api/auth/register",
            json={"username": username, "password": password, "email": email},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ========== 对话 ==========
    def get_conversations(self) -> list:
        """获取历史对话列表"""
        resp = requests.get(
            f"{self.base_url}/api/conversations",
            headers=self.headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def send_message(self, conversation_id: str, message: str, product_url: str = None) -> dict:
        """发送消息（普通对话或商品分析）"""
        payload = {"message": message}
        if product_url:
            payload["product_url"] = product_url
        resp = requests.post(
            f"{self.base_url}/api/conversations/{conversation_id}/messages",
            json=payload,
            headers=self.headers,
            timeout=300,  # 分析任务可能耗时较长
        )
        resp.raise_for_status()
        return resp.json()

    # ========== 分析 ==========
    def start_analysis(self, product_url: str, question: str) -> dict:
        """启动商品分析"""
        resp = requests.post(
            f"{self.base_url}/api/analysis/start",
            json={"product_url": product_url, "question": question},
            headers=self.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_analysis_status(self, task_id: str) -> dict:
        """获取分析任务状态"""
        resp = requests.get(
            f"{self.base_url}/api/analysis/{task_id}/status",
            headers=self.headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
'''
