'''
"""Streamlit frontend entrypoint."""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

from config import APP_TITLE
from utils.api_client_v2 import APIClient, APIClientError

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="AI",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_state() -> None:
    defaults = {
        "token": None,
        "user": None,
        "conversation_id": None,
        "conversation_detail": None,
        "conversation_list": [],
        "task_progress_cache": {},
        "task_result_cache": {},
        "flash_message": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_client() -> APIClient:
    return APIClient(token=st.session_state.token)


def set_flash(kind: str, text: str) -> None:
    st.session_state.flash_message = {"kind": kind, "text": text}


def show_flash() -> None:
    flash = st.session_state.flash_message
    if not flash:
        return
    getattr(st, flash["kind"])(flash["text"])
    st.session_state.flash_message = None


def refresh_conversations() -> None:
    payload = get_client().list_conversations()
    data = payload["data"]
    st.session_state.conversation_list = data["items"]

    if not st.session_state.conversation_id and data["items"]:
        st.session_state.conversation_id = data["items"][0]["id"]


def refresh_conversation_detail() -> None:
    conversation_id = st.session_state.conversation_id
    if not conversation_id:
        st.session_state.conversation_detail = None
        return

    payload = get_client().get_conversation_detail(conversation_id)
    st.session_state.conversation_detail = payload["data"]


def ensure_active_conversation() -> int:
    if st.session_state.conversation_id:
        return st.session_state.conversation_id

    payload = get_client().create_conversation()
    conversation = payload["data"]
    st.session_state.conversation_id = conversation["id"]
    refresh_conversations()
    refresh_conversation_detail()
    return conversation["id"]


def poll_tasks(tasks: list[dict[str, Any]]) -> bool:
    has_active_task = False
    client = get_client()

    for task in tasks:
        task_id = task["task_id"]
        progress_payload = client.get_task_progress(task_id)
        progress = progress_payload["data"]
        st.session_state.task_progress_cache[task_id] = progress

        if progress["status"] in {"pending", "processing"}:
            has_active_task = True

        if progress["report_ready"]:
            result_payload = client.get_task_result(task_id)
            if result_payload["_http_status"] == 200 and result_payload["data"] is not None:
                st.session_state.task_result_cache[task_id] = result_payload["data"]

    return has_active_task


def render_auth_view() -> None:
    st.title(APP_TITLE)
    st.caption("基于统一消息入口的电商舆情分析前端")

    login_tab, register_tab = st.tabs(["登录", "注册"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", use_container_width=True)
            if submitted:
                try:
                    payload = APIClient().login(username.strip(), password)
                    auth = payload["data"]
                    st.session_state.token = auth["access_token"]
                    st.session_state.user = auth["user"]
                    refresh_conversations()
                    refresh_conversation_detail()
                    set_flash("success", "登录成功")
                    st.rerun()
                except APIClientError as exc:
                    st.error(str(exc))

    with register_tab:
        with st.form("register_form"):
            username = st.text_input("新用户名")
            email = st.text_input("邮箱")
            password = st.text_input("新密码", type="password")
            submitted = st.form_submit_button("注册", use_container_width=True)
            if submitted:
                try:
                    APIClient().register(username.strip(), email.strip(), password)
                    set_flash("success", "注册成功，请直接登录")
                    st.rerun()
                except APIClientError as exc:
                    st.error(str(exc))


def render_sidebar() -> None:
    with st.sidebar:
        st.subheader("当前用户")
        st.write(st.session_state.user["username"])
        st.caption(st.session_state.user["email"])

        col1, col2 = st.columns(2)
        if col1.button("新建会话", use_container_width=True):
            try:
                payload = get_client().create_conversation()
                st.session_state.conversation_id = payload["data"]["id"]
                refresh_conversations()
                refresh_conversation_detail()
                set_flash("success", "已创建新会话")
                st.rerun()
            except APIClientError as exc:
                set_flash("error", str(exc))
                st.rerun()
        if col2.button("刷新列表", use_container_width=True):
            try:
                refresh_conversations()
                refresh_conversation_detail()
                st.rerun()
            except APIClientError as exc:
                set_flash("error", str(exc))
                st.rerun()

        if st.button("退出登录", use_container_width=True):
            st.session_state.token = None
            st.session_state.user = None
            st.session_state.conversation_id = None
            st.session_state.conversation_detail = None
            st.session_state.conversation_list = []
            st.session_state.task_progress_cache = {}
            st.session_state.task_result_cache = {}
            set_flash("success", "已退出登录")
            st.rerun()

        st.divider()
        st.subheader("会话列表")
        for item in st.session_state.conversation_list:
            label = item["title"] or f"会话 {item['id']}"
            latest_task = item.get("latest_task")
            if latest_task:
                label = f"{label} [{latest_task['status']}]"
            if st.button(
                label,
                key=f"conversation_{item['id']}",
                use_container_width=True,
                type="primary" if item["id"] == st.session_state.conversation_id else "secondary",
            ):
                st.session_state.conversation_id = item["id"]
                refresh_conversation_detail()
                st.rerun()


def render_message(message: dict[str, Any]) -> None:
    role_map = {
        "user": "user",
        "assistant": "assistant",
        "system": "assistant",
    }
    with st.chat_message(role_map.get(message["role"], "assistant")):
        st.markdown(message["content"])
        st.caption(f"{message['message_type']} | {message['created_at']}")


def render_task_panel(task: dict[str, Any]) -> None:
    task_id = task["task_id"]
    progress = st.session_state.task_progress_cache.get(task_id, task)
    result = st.session_state.task_result_cache.get(task_id)
    status = progress["status"]

    with st.expander(f"任务 {task_id} | {status} | {progress['progress']}%", expanded=status != "completed"):
        st.progress(int(progress["progress"]) / 100)
        st.write(f"问题：{task['question']}")
        st.write(f"当前步骤：{progress.get('current_step') or 'queued'}")

        for step in progress.get("steps", []):
            st.write(f"- {step['label']}：{step['status']}")

        if status == "failed":
            st.error(progress.get("error_message") or "任务失败")
            if st.button("重试任务", key=f"retry_{task_id}", use_container_width=True):
                try:
                    get_client().retry_task(task_id)
                    set_flash("success", f"任务 {task_id} 已重新提交")
                    refresh_conversation_detail()
                    st.rerun()
                except APIClientError as exc:
                    set_flash("error", str(exc))
                    st.rerun()

        if result:
            st.success("分析结果已就绪")
            st.markdown(result.get("summary") or "暂无摘要")

            product = result.get("product") or {}
            if product:
                st.write(
                    f"商品：{product.get('product_name') or product.get('external_product_id')} "
                    f"({product.get('source')})"
                )

            statistics = result.get("statistics") or {}
            if statistics:
                st.json(statistics)

            evidence = result.get("evidence") or []
            if evidence:
                st.write("证据评论")
                for item in evidence[:5]:
                    st.write(
                        f"- [{item.get('dimension') or '未分类'} / {item.get('score')}] {item.get('content')}"
                    )


def render_conversation_tools(detail: dict[str, Any]) -> None:
    with st.expander("会话操作", expanded=False):
        with st.form("rename_form"):
            new_title = st.text_input("会话标题", value=detail.get("title") or "")
            rename_submitted = st.form_submit_button("保存标题", use_container_width=True)
            if rename_submitted and new_title.strip():
                try:
                    get_client().update_conversation(detail["id"], new_title.strip())
                    refresh_conversations()
                    refresh_conversation_detail()
                    set_flash("success", "会话标题已更新")
                    st.rerun()
                except APIClientError as exc:
                    st.error(str(exc))

        if st.button("删除当前会话", type="secondary", use_container_width=True):
            try:
                get_client().delete_conversation(detail["id"])
                st.session_state.conversation_id = None
                st.session_state.conversation_detail = None
                st.session_state.task_progress_cache = {}
                st.session_state.task_result_cache = {}
                refresh_conversations()
                set_flash("success", "会话已删除")
                st.rerun()
            except APIClientError as exc:
                set_flash("error", str(exc))
                st.rerun()


def render_main_view() -> None:
    st.title(APP_TITLE)
    show_flash()

    if not st.session_state.conversation_list:
        st.info("当前没有会话，先在左侧创建一个。")
        return

    if not st.session_state.conversation_detail:
        refresh_conversation_detail()

    detail = st.session_state.conversation_detail
    if not detail:
        st.warning("未能加载会话详情")
        return

    st.subheader(detail.get("title") or f"会话 {detail['id']}")
    render_conversation_tools(detail)

    messages = detail.get("messages", [])
    tasks = detail.get("tasks", [])
    has_active_task = poll_tasks(tasks) if tasks else False

    message_col, task_col = st.columns([2, 1])
    with message_col:
        st.markdown("### 消息流")
        for message in messages:
            render_message(message)

    with task_col:
        st.markdown("### 分析任务")
        if not tasks:
            st.caption("当前会话还没有分析任务。")
        for task in tasks:
            render_task_panel(task)

    prompt = st.chat_input("输入普通问题，或直接发送商品链接加分析问题")
    if prompt:
        try:
            conversation_id = ensure_active_conversation()
            payload = get_client().send_message(conversation_id, prompt.strip())
            mode = payload["data"]["handling_mode"]
            refresh_conversations()
            refresh_conversation_detail()
            if mode == "task_created":
                set_flash("success", "分析任务已创建，前端将自动轮询状态")
            else:
                set_flash("success", "消息已发送")
            st.rerun()
        except APIClientError as exc:
            set_flash("error", str(exc))
            st.rerun()

    if has_active_task:
        st.caption("检测到进行中的分析任务，3 秒后自动刷新。")
        time.sleep(3)
        refresh_conversation_detail()
        st.rerun()


def bootstrap_authenticated_view() -> None:
    try:
        if not st.session_state.conversation_list:
            refresh_conversations()
        if st.session_state.conversation_id and not st.session_state.conversation_detail:
            refresh_conversation_detail()
    except APIClientError as exc:
        st.session_state.token = None
        st.session_state.user = None
        set_flash("error", f"认证已失效：{exc}")
        st.rerun()


def main() -> None:
    init_state()
    show_flash()
    if st.session_state.user is None or st.session_state.token is None:
        render_auth_view()
        return

    bootstrap_authenticated_view()
    render_sidebar()
    render_main_view()
'''

from app_runtime import main
