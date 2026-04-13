"""普通聊天回复服务，优先调用 LLM，失败时安全降级。"""

from __future__ import annotations

from typing import Any

from app.config import DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, DEEPSEEK_MODEL
from app.models import Conversation, Message
from app.models.conversation import MessageRole
from app.utils.logger import logger


class ChatService:
    """负责生成非分析类消息的直接回复。"""

    MAX_HISTORY_MESSAGES = 6

    @staticmethod
    def _build_system_prompt(conversation: Conversation) -> str:
        """构造发送给聊天模型的系统提示词。"""
        prompt = (
            "You are the MA-ESAS assistant. Answer clearly and directly in the user's language. "
            "Focus on product analysis, e-commerce questions, and system usage guidance. "
            "If the request needs product-specific analysis but no supported product link is provided, "
            "ask the user to send a supported product link together with a concrete question."
        )
        if conversation.bound_product_id:
            prompt += (
                f" The current conversation is already bound to product_id={conversation.bound_product_id}. "
                "Prefer continuing that product context unless the user clearly asks to switch."
            )
        return prompt

    @staticmethod
    def _fallback_reply(conversation: Conversation, user_content: str) -> str:
        """在模型不可用时返回可读的降级回复。"""
        if conversation.bound_product_id:
            return (
                "我暂时无法调用在线对话模型，但已收到你的消息。"
                f"当前会话已绑定商品 product_id={conversation.bound_product_id}，"
                "你可以继续补充更具体的问题，或稍后重试。"
            )
        return (
            "我暂时无法调用在线对话模型，但已收到你的消息。"
            "如果你想发起商品分析，请直接发送受支持的商品链接和具体问题；"
            "如果是普通问答，也可以稍后重试。"
        )

    @staticmethod
    def _is_fallback_reply(content: str) -> bool:
        """判断一条助手消息是否为本地降级回复，避免继续污染后续上下文。"""
        normalized = content.strip()
        if not normalized:
            return False
        fallback_markers = (
            "我暂时无法调用在线对话模型",
            "但已收到你的消息",
            "如果你想发起商品分析，请直接发送受支持的商品链接和具体问题",
        )
        return all(marker in normalized for marker in fallback_markers)

    @staticmethod
    def _normalize_content(content: Any) -> str:
        """规范化模型返回内容，兼容字符串和分段消息结构。"""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item.strip())
                    continue
                if isinstance(item, dict) and item.get("type") == "text":
                    text = str(item.get("text", "")).strip()
                    if text:
                        parts.append(text)
            return "\n".join(part for part in parts if part).strip()
        return str(content).strip()

    @classmethod
    def generate_reply(
        cls,
        conversation: Conversation,
        user_content: str,
        history_messages: list[Message] | None = None,
    ) -> str:
        """生成普通聊天回复，并在依赖缺失或调用失败时自动回退。"""
        if not DEEPSEEK_API_KEY:
            logger.warning("Direct chat is falling back because DEEPSEEK_API_KEY is not configured.")
            return cls._fallback_reply(conversation, user_content)

        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            logger.warning("Direct chat is falling back because LLM dependencies are unavailable: {}", exc)
            return cls._fallback_reply(conversation, user_content)

        messages: list[Any] = [SystemMessage(content=cls._build_system_prompt(conversation))]
        for item in history_messages or []:
            if item.role == MessageRole.USER:
                messages.append(HumanMessage(content=item.content))
            elif item.role == MessageRole.ASSISTANT:
                if cls._is_fallback_reply(item.content):
                    logger.info("Skip fallback reply in chat history to avoid context contamination.")
                    continue
                messages.append(AIMessage(content=item.content))
        messages.append(HumanMessage(content=user_content))

        client = ChatOpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_API_BASE,
            model=DEEPSEEK_MODEL,
            temperature=0.3,
            timeout=30,
            max_retries=1,
        )

        try:
            response = client.invoke(messages)
        except Exception as exc:
            logger.exception("Direct chat model call failed: {}", exc)
            return cls._fallback_reply(conversation, user_content)

        logger.info("模型返回内容{}", response.content)
        content = cls._normalize_content(response.content)
        if not content:
            logger.warning("Direct chat returned empty content, using fallback reply instead.")
            return cls._fallback_reply(conversation, user_content)
        return content
