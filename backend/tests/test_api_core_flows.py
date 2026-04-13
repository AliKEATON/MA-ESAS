from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.chat_service import ChatService


def register_and_login(client: TestClient, username: str = "tester") -> tuple[dict, dict]:
    register_payload = {
        "username": username,
        "email": f"{username}@example.com",
        "password": "password123",
    }
    register_response = client.post("/api/auth/register", json=register_payload)
    assert register_response.status_code == 200, register_response.text

    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "password123"},
    )
    assert login_response.status_code == 200, login_response.text

    token = login_response.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, login_response.json()


def create_conversation(client: TestClient, headers: dict) -> dict:
    response = client.post("/api/conversations", json={"bound_product_id": None}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_auth_register_login_and_me(client: TestClient) -> None:
    headers, login_payload = register_and_login(client, username="auth_user")

    me_response = client.get("/api/auth/me", headers=headers)
    assert me_response.status_code == 200, me_response.text

    me_data = me_response.json()["data"]
    assert me_data["username"] == "auth_user"
    assert login_payload["data"]["user"]["email"] == "auth_user@example.com"


def test_conversation_direct_reply_flow(client: TestClient) -> None:
    original_generate_reply = ChatService.generate_reply
    ChatService.generate_reply = classmethod(lambda cls, conversation, user_content, history_messages=None: "mocked llm reply")
    headers, _ = register_and_login(client, username="chat_user")
    try:
        conversation = create_conversation(client, headers)

        send_response = client.post(
            f"/api/conversations/{conversation['id']}/messages",
            json={"content": "Please summarize what this system does."},
            headers=headers,
        )
        assert send_response.status_code == 201, send_response.text

        payload = send_response.json()["data"]
        assert payload["handling_mode"] == "direct_reply"
        assert payload["user_message"]["message_type"] == "chat"
        assert payload["reply_message"]["role"] == "assistant"
        assert payload["reply_message"]["content"] == "mocked llm reply"

        detail_response = client.get(f"/api/conversations/{conversation['id']}", headers=headers)
        assert detail_response.status_code == 200, detail_response.text

        detail_data = detail_response.json()["data"]
        assert len(detail_data["messages"]) == 2
        assert detail_data["messages"][1]["content"] == "mocked llm reply"
        assert detail_data["tasks"] == []
    finally:
        ChatService.generate_reply = original_generate_reply


def test_analysis_task_creation_and_progress_query(client: TestClient) -> None:
    headers, _ = register_and_login(client, username="analysis_user")
    conversation = create_conversation(client, headers)

    send_response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "https://item.jd.com/100197744867.html Is this product worth buying?"},
        headers=headers,
    )
    assert send_response.status_code == 202, send_response.text

    payload = send_response.json()["data"]
    assert payload["handling_mode"] == "task_created"
    assert payload["user_message"]["message_type"] == "analysis_request"
    assert payload["reply_message"]["message_type"] == "system_notice"

    task_id = payload["analysis_task"]["task_id"]

    progress_response = client.get(f"/api/analysis/tasks/{task_id}", headers=headers)
    assert progress_response.status_code == 200, progress_response.text

    progress_data = progress_response.json()["data"]
    assert progress_data["task_id"] == task_id
    assert progress_data["status"] in {"pending", "processing"}
    assert isinstance(progress_data["steps"], list)
    assert len(progress_data["steps"]) > 0

    tasks_response = client.get(f"/api/conversations/{conversation['id']}/tasks", headers=headers)
    assert tasks_response.status_code == 200, tasks_response.text
    assert tasks_response.json()["data"][0]["task_id"] == task_id


def test_analysis_result_not_ready_returns_202(client: TestClient) -> None:
    headers, _ = register_and_login(client, username="result_user")
    conversation = create_conversation(client, headers)

    send_response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "https://item.jd.com/100197744867.html Give me an analysis."},
        headers=headers,
    )
    task_id = send_response.json()["data"]["analysis_task"]["task_id"]

    result_response = client.get(f"/api/analysis/tasks/{task_id}/result", headers=headers)
    assert result_response.status_code == 202, result_response.text
    assert result_response.json()["message"] == "Analysis result is not ready"


def test_failed_task_can_be_retried(client: TestClient) -> None:
    headers, _ = register_and_login(client, username="retry_user")
    conversation = create_conversation(client, headers)

    send_response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "https://item.jd.com/100197744867.html Analyze the negative reviews."},
        headers=headers,
    )
    task_id = send_response.json()["data"]["analysis_task"]["task_id"]

    progress_response = client.get(f"/api/analysis/tasks/{task_id}", headers=headers)
    assert progress_response.status_code == 200, progress_response.text

    # Mark the task as failed through the retry API precondition path by first querying detail
    # and then updating task state through the application's own retry entry is not possible,
    # so we drive the failure state through the database-facing route indirectly.
    from app.main import app
    from app.models import AnalysisTask
    from app.models.analysis_task import AnalysisTaskStatus

    db = app.state.testing_sessionmaker()
    try:
        task = db.query(AnalysisTask).filter_by(task_id=task_id).first()
        task.status = AnalysisTaskStatus.FAILED
        task.error_message = "forced test failure"
        db.commit()
    finally:
        db.close()

    retry_response = client.post(f"/api/analysis/tasks/{task_id}/retry", headers=headers)
    assert retry_response.status_code == 202, retry_response.text

    retry_data = retry_response.json()["data"]
    assert retry_data["task_id"] == task_id
    assert retry_data["status"] == "pending"
    assert retry_data["progress"] == 0
