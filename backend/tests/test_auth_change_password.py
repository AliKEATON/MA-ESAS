from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth as auth_api
from app.db.database import get_db
from app.models import Base


def _build_test_client() -> TestClient:
    """构建使用内存数据库的认证测试客户端。"""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(auth_api.router)

    def override_get_db():
        """为测试环境提供独立数据库会话。"""

        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _register_and_login(client: TestClient, username: str = "testuser"):
    """完成测试用户注册和登录。"""

    register_response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "password123",
        },
    )
    assert register_response.status_code == 200

    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "password123"},
    )
    assert login_response.status_code == 200
    return login_response.json()["data"]["access_token"]


def test_change_password_success():
    """验证用户可以使用正确旧密码修改密码。"""

    client = _build_test_client()
    token = _register_and_login(client)

    response = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "password123",
            "new_password": "new-password-456",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 200
    assert response.json()["data"]["success"] is True

    old_login_response = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "password123"},
    )
    assert old_login_response.status_code == 401

    new_login_response = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "new-password-456"},
    )
    assert new_login_response.status_code == 200


def test_change_password_rejects_wrong_current_password():
    """验证旧密码错误时拒绝修改密码。"""

    client = _build_test_client()
    token = _register_and_login(client, username="wrongpass")

    response = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "wrong-password",
            "new_password": "new-password-456",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "当前密码错误"


def test_change_password_rejects_same_password():
    """验证新旧密码相同时拒绝修改密码。"""

    client = _build_test_client()
    token = _register_and_login(client, username="samepass")

    response = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "password123",
            "new_password": "password123",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "新密码不能与当前密码相同"
