"""模型工厂：统一经 ChatOpenAI 对接 DeepSeek（OpenAI 兼容协议）。"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from .config import Settings

# DeepSeek 的 OpenAI 兼容接口不支持 json_schema 响应格式。实测（2026-09-28）：
#   - 默认 method="json_schema" → 400 This response_format type is unavailable now
#   - method="json_mode"        → 同样失败
#   - method="function_calling" → 正常
# langchain 的 with_structured_output 默认走 json_schema，因此必须显式指定
# function_calling，否则 plan / reflect 两个节点在真实模型上直接 400。
STRUCTURED_OUTPUT_METHOD = "function_calling"


def structured_output[SchemaT: BaseModel](
    model: BaseChatModel, schema: type[SchemaT]
) -> Runnable[Any, SchemaT]:
    """按 DeepSeek 可用的方式获得结构化输出（勿直接用 with_structured_output 默认值）。"""
    return model.with_structured_output(schema, method=STRUCTURED_OUTPUT_METHOD)  # type: ignore[return-value]


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
