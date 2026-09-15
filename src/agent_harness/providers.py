"""模型 Provider 抽象。

内部统一使用 OpenAI Chat Completions 风格的消息格式,DeepSeek 可直接透传:
- user/assistant: {"role", "content"}
- 工具调用(助手侧): {"role":"assistant","content", "tool_calls":[{"id","type","function":{"name","arguments"}}]}
- 工具结果: {"role":"tool","tool_call_id","content"}

后续接入 Anthropic 时新建一个 Provider 子类,在 complete() 内做格式转换即可,
Agent 主循环无需改动(对应简历: 新增 provider 即插即用)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import OpenAI

from .config import Settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON 字符串,由调用方解析


@dataclass
class AssistantReply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class ModelProvider(Protocol):
    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantReply:
        ...


class OpenAICompatibleProvider:
    """适配 DeepSeek / GLM / MiniMax 等 OpenAI 兼容型 API。"""

    def __init__(self, settings: Settings) -> None:
        self._client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
        self._model = settings.model
        self._max_tokens = settings.max_tokens
        self._temperature = settings.temperature

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantReply:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools if tools else None,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )
        msg = resp.choices[0].message
        tool_calls = [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=tc.function.arguments,
            )
            for tc in (msg.tool_calls or [])
        ]
        return AssistantReply(content=msg.content, tool_calls=tool_calls)