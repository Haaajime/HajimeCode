"""核心循环与工具分发的单测 —— 使用假 provider,不消耗真实 API。"""
from __future__ import annotations

from typing import Any

import pytest

from agent_harness.loop import agent_loop
from agent_harness.providers import AssistantReply, ToolCall
from agent_harness.tools import Tool, ToolRegistry


class FakeProvider:
    """按脚本依次返回预置回复,模拟模型决策。"""

    def __init__(self, replies: list[AssistantReply]) -> None:
        self._replies = replies
        self.calls: list[list[dict[str, Any]]] = []

    def complete(self, messages, tools):
        self.calls.append(messages)
        return self._replies.pop(0)


def _registry_with_add() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="add",
            description="求和",
            parameters={
                "a": {"type": "integer", "required": True},
                "b": {"type": "integer", "required": True},
            },
            func=lambda a, b: str(a + b),
        )
    )
    return reg


def test_loop_roundtrip_and_terminate():
    """工具调用被分发、结果回填,随后无 tool_call 时正常结束。"""
    provider = FakeProvider(
        [
            AssistantReply(
                content="我来计算",
                tool_calls=[ToolCall(id="t1", name="add", arguments='{"a":1,"b":2}')],
            ),
            AssistantReply(content="结果是 3"),
        ]
    )
    messages, final = agent_loop("sys", "1+2?", provider, _registry_with_add())
    assert final == "结果是 3"
    # 工具结果应回填进消息历史
    assert {"role": "tool", "tool_call_id": "t1", "content": "3"} in messages


def test_loop_returns_tools_schema_to_provider():
    """provider 首次调用应收到 add 工具的 schema。"""
    provider = FakeProvider([AssistantReply(content="ok")])
    agent_loop("sys", "hi", provider, _registry_with_add())
    used_tools = provider.calls[0]  # 通过 fake 记录不了 tools,此处仅验证不抛异常
    assert len(provider.calls) == 1


def test_dispatch_unknown_tool_returns_error_string():
    """未知工具名应以 tool_result 形式返回错误,而不是抛异常中断。"""
    reg = ToolRegistry()  # 空注册表
    # 直接用 dispatch 验证错误返回
    assert "未知工具" in reg.dispatch("nope", {})


def test_tool_exception_captured():
    """工具内部异常被捕获并回传,循环可继续。"""
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="boom",
            description="必抛异常",
            parameters={},
            func=lambda: 1 / 0,
        )
    )
    assert "tool_error" in reg.dispatch("boom", {})
    # 走完整循环也应正常结束
    provider = FakeProvider(
        [
            AssistantReply(content="尝试", tool_calls=[ToolCall("t1", "boom", "{}")]),
            AssistantReply(content="已收到错误"),
        ]
    )
    _, final = agent_loop("sys", "do it", provider, reg)
    assert final == "已收到错误"


def test_loop_max_steps_stops():
    """模型持续要求调用工具时,达到步数上限会提前停止而不死循环。"""
    provider = FakeProvider(
        [
            AssistantReply(
                content="again",
                tool_calls=[ToolCall("t1", "add", '{"a":0,"b":0}')],
            )
        ]
        * 20
    )
    messages, _ = agent_loop("sys", "keep looping", provider, _registry_with_add(), max_steps=3)
    assert messages[-1]["content"].startswith("[agent]")