"""Agent 主循环: message→LLM→tool_use→执行→tool_result 回填→继续。

内部消息一律使用 OpenAI Chat 风格(dict),与 provider 解耦。这里不感知具体模型,
只做"分发工具结果并回填"这一件事,对应简历: 核心循环 + 工具分发。
"""
from __future__ import annotations

import json
from typing import Any

from .providers import ModelProvider
from .tools import ToolRegistry

_TIMEOUT_NOTE = "[agent] 达到最大循环步数,提前停止。"


def agent_loop(
    system: str,
    user_prompt: str,
    provider: ModelProvider,
    registry: ToolRegistry,
    max_steps: int = 10,
) -> tuple[list[dict[str, Any]], str | None]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]
    last_text: str | None = None

    for _ in range(max_steps):
        tools = registry.schemas()
        reply = provider.complete(messages, tools) if tools else provider.complete(messages, [])

        assistant: dict[str, Any] = {"role": "assistant", "content": reply.content}
        if reply.has_tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in reply.tool_calls
            ]
        messages.append(assistant)
        last_text = reply.content

        if not reply.has_tool_calls:
            return messages, last_text

        for tc in reply.tool_calls:
            try:
                args = json.loads(tc.arguments) if tc.arguments else {}
            except json.JSONDecodeError:
                args = {}
            result = registry.dispatch(tc.name, args)
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result}
            )

    messages.append({"role": "user", "content": _TIMEOUT_NOTE})
    return messages, last_text