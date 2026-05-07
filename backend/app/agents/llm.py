"""多 Agent 工作流共享的 LLM 调用辅助工具。"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from app.config import DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, DEEPSEEK_MODEL, LLM_TIMEOUT_SECONDS
from app.utils.logger import logger

SchemaT = TypeVar("SchemaT")


class LLMUnavailableError(RuntimeError):
    """当当前环境无法正常使用大模型时抛出该异常。"""


# 统一对外暴露底层对话模型，避免各 Agent 分散维护初始化逻辑。
def get_chat_model(*, temperature: float = 0.1):
    """构造所有 Agent 共享的 Chat 模型实例。"""
    if not DEEPSEEK_API_KEY:
        raise LLMUnavailableError("DEEPSEEK_API_KEY is not configured")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise LLMUnavailableError(f"langchain_openai is unavailable: {exc}") from exc

    return ChatOpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_API_BASE,
        model=DEEPSEEK_MODEL,
        temperature=temperature,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )


# 统一封装“结构化输出 + Pydantic 解析”，让各 Agent 专注协议本身。
def invoke_structured_output(
    *,
    system_prompt: str,
    payload: dict[str, Any],
    schema: type[SchemaT],
    temperature: float = 0.1,
) -> SchemaT:
    """以结构化输出方式调用大模型，并直接解析为指定的 Pydantic 模型。"""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError as exc:
        raise LLMUnavailableError(f"langchain_core is unavailable: {exc}") from exc

    model = get_chat_model(temperature=temperature)
    structured_model = model.with_structured_output(schema)
    messages = [
        SystemMessage(content=system_prompt.strip()),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, indent=2)),
    ]
    logger.info(
        "Invoking structured LLM output: schema={} model={}",
        getattr(schema, "__name__", str(schema)),
        DEEPSEEK_MODEL,
    )
    return structured_model.invoke(messages)
