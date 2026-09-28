"""模型工厂：统一经 ChatOpenAI 对接 DeepSeek（OpenAI 兼容协议）。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import Settings


def build_chat_model(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.require_api_key(),
        base_url=settings.base_url,
        temperature=settings.temperature,
        max_completion_tokens=settings.max_tokens,
        timeout=settings.timeout_s,
        max_retries=settings.max_retries,
    )
