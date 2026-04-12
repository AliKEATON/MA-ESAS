"""HTTP client for the Streamlit frontend."""

from __future__ import annotations

from typing import Any

import requests

from config import FASTAPI_BASE_URL


class APIClientError(RuntimeError):
    """Raised when the backend request fails."""


class APIClient:
    """Thin wrapper around the FastAPI backend."""

    def __init__(self, token: str | None = None):
        self.base_url = FASTAPI_BASE_URL.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        timeout: int = 15,
        allow_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        allowed = allow_statuses or {200, 201, 202}
        response = requests.request(
            method=method,
            url=f"{self.base_url}{path}",
            json=json,
            headers=self._headers(),
            timeout=timeout,
        )

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.status_code not in allowed:
            message = "Request failed"
            if isinstance(payload, dict):
                message = payload.get("detail") or payload.get("message") or message
            raise APIClientError(f"{response.status_code}: {message}")

        if not isinstance(payload, dict):
            raise APIClientError("Backend returned an invalid JSON payload")

        payload["_http_status"] = response.status_code
        return payload

    def health_check(self) -> dict[str, Any]:
        return self._request("GET", "/health", allow_statuses={200})

    def login(self, username: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/auth/login",
            json={"username": username, "password": password},
        )

    def register(self, username: str, email: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/auth/register",
            json={"username": username, "email": email, "password": password},
        )

    def get_current_user(self) -> dict[str, Any]:
        return self._request("GET", "/api/auth/me")

    def list_conversations(self, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        return self._request("GET", f"/api/conversations?page={page}&page_size={page_size}")

    def create_conversation(self, bound_product_id: int | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/conversations",
            json={"bound_product_id": bound_product_id},
        )

    def get_conversation_detail(self, conversation_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/conversations/{conversation_id}")

    def update_conversation(self, conversation_id: int, title: str) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"/api/conversations/{conversation_id}",
            json={"title": title},
        )

    def delete_conversation(self, conversation_id: int) -> dict[str, Any]:
        return self._request("DELETE", f"/api/conversations/{conversation_id}")

    def send_message(self, conversation_id: int, content: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/conversations/{conversation_id}/messages",
            json={"content": content},
            timeout=60,
        )

    def get_task_progress(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/analysis/tasks/{task_id}")

    def get_task_result(self, task_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/analysis/tasks/{task_id}/result",
            allow_statuses={200, 202},
        )

    def retry_task(self, task_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/analysis/tasks/{task_id}/retry")
