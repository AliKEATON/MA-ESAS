from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import app.services.chat_service as chat_service_module
from app.models import Conversation, Message
from app.models.conversation import MessageRole, MessageType
from app.services.chat_service import ChatService


def _build_conversation(bound_product_id: int | None = None) -> Conversation:
    """构造用于测试的会话对象。"""
    return Conversation(id=1, user_id=1, bound_product_id=bound_product_id)


def _build_message(role: MessageRole, content: str) -> Message:
    """构造用于测试的历史消息对象。"""
    return Message(
        conversation_id=1,
        role=role,
        content=content,
        message_type=MessageType.CHAT,
    )


def _install_fake_langchain(
    monkeypatch,
    *,
    response_content: object = "mocked reply",
    invoke_error: Exception | None = None,
):
    """安装假的 LangChain 依赖，避免单元测试访问真实网络。"""
    messages_module = types.ModuleType("langchain_core.messages")

    class _BaseMessage:
        """模拟 LangChain 消息对象，仅保留 content 字段。"""

        def __init__(self, content: str):
            self.content = content

    class FakeSystemMessage(_BaseMessage):
        """模拟系统消息。"""

    class FakeHumanMessage(_BaseMessage):
        """模拟用户消息。"""

    class FakeAIMessage(_BaseMessage):
        """模拟助手消息。"""

    class FakeChatOpenAI:
        """模拟聊天模型客户端，记录调用参数并返回预设结果。"""

        last_kwargs: dict | None = None
        last_messages: list | None = None

        def __init__(self, **kwargs):
            """记录模型初始化参数。"""
            type(self).last_kwargs = kwargs

        def invoke(self, messages):
            """记录消息列表，并返回模拟响应或抛出预设异常。"""
            type(self).last_messages = messages
            if invoke_error is not None:
                raise invoke_error
            return SimpleNamespace(content=response_content)

    messages_module.SystemMessage = FakeSystemMessage
    messages_module.HumanMessage = FakeHumanMessage
    messages_module.AIMessage = FakeAIMessage

    openai_module = types.ModuleType("langchain_openai")
    openai_module.ChatOpenAI = FakeChatOpenAI

    monkeypatch.setitem(sys.modules, "langchain_core.messages", messages_module)
    monkeypatch.setitem(sys.modules, "langchain_openai", openai_module)
    return FakeChatOpenAI


def test_generate_reply_returns_fallback_when_api_key_missing(monkeypatch) -> None:
    """未配置 API Key 时，应直接降级并打印明确告警。"""
    warnings: list[tuple[str, tuple]] = []

    monkeypatch.setattr(chat_service_module, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(chat_service_module.logger, "warning", lambda message, *args: warnings.append((message, args)))

    conversation = _build_conversation()
    reply = ChatService.generate_reply(conversation, "你好，请介绍一下你自己。")

    assert reply == ChatService._fallback_reply(conversation, "你好，请介绍一下你自己。")
    assert warnings
    assert "DEEPSEEK_API_KEY is not configured" in warnings[0][0]


def test_generate_reply_calls_llm_with_recent_history(monkeypatch) -> None:
    """配置完整且依赖可用时，应调用聊天模型并携带上下文消息。"""
    fake_client = _install_fake_langchain(
        monkeypatch,
        response_content=[{"type": "text", "text": "  模型回复  "}],
    )
    monkeypatch.setattr(chat_service_module, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(chat_service_module, "DEEPSEEK_API_BASE", "https://api.siliconflow.cn/v1")
    monkeypatch.setattr(chat_service_module, "DEEPSEEK_MODEL", "deepseek-ai/DeepSeek-V3")

    conversation = _build_conversation(bound_product_id=10)
    history_messages = [
        _build_message(MessageRole.USER, "第一轮提问"),
        _build_message(MessageRole.ASSISTANT, "第一轮回答"),
    ]

    reply = ChatService.generate_reply(
        conversation,
        "请继续分析。",
        history_messages,
    )

    assert reply == "模型回复"
    assert fake_client.last_kwargs == {
        "api_key": "test-key",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
        "temperature": 0.3,
        "timeout": 30,
        "max_retries": 1,
    }
    assert [message.content for message in fake_client.last_messages] == [
        ChatService._build_system_prompt(conversation),
        "第一轮提问",
        "第一轮回答",
        "请继续分析。",
    ]


def test_generate_reply_logs_exception_and_falls_back_when_invoke_fails(monkeypatch) -> None:
    """模型调用抛错时，应记录异常日志并回退到安全回复。"""
    exceptions: list[tuple[str, tuple]] = []

    _install_fake_langchain(
        monkeypatch,
        invoke_error=RuntimeError("upstream boom"),
    )
    monkeypatch.setattr(chat_service_module, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(chat_service_module.logger, "exception", lambda message, *args: exceptions.append((message, args)))

    conversation = _build_conversation()
    reply = ChatService.generate_reply(conversation, "这条消息会触发异常吗？")

    assert reply == ChatService._fallback_reply(conversation, "这条消息会触发异常吗？")
    assert exceptions
    assert "Direct chat model call failed" in exceptions[0][0]


def test_generate_reply_skips_fallback_messages_in_history(monkeypatch) -> None:
    """历史消息中的本地降级回复不应再次传给模型。"""
    fake_client = _install_fake_langchain(
        monkeypatch,
        response_content="新的正常回复",
    )
    monkeypatch.setattr(chat_service_module, "DEEPSEEK_API_KEY", "test-key")

    conversation = _build_conversation()
    fallback_message = ChatService._fallback_reply(conversation, "上一轮问题")
    history_messages = [
        _build_message(MessageRole.USER, "上一轮问题"),
        _build_message(MessageRole.ASSISTANT, fallback_message),
        _build_message(MessageRole.ASSISTANT, "正常历史回答"),
    ]

    reply = ChatService.generate_reply(
        conversation,
        "这一轮请正常回答。",
        history_messages,
    )

    assert reply == "新的正常回复"
    assert [message.content for message in fake_client.last_messages] == [
        ChatService._build_system_prompt(conversation),
        "上一轮问题",
        "正常历史回答",
        "这一轮请正常回答。",
    ]
