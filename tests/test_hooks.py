"""Hooks 事件钩子单测 —— 全部离线 mock,零 API 消耗。"""
from __future__ import annotations

from agent_harness.hooks import Hooks, HookAction, HookResult
from agent_harness.loop import agent_loop
from agent_harness.providers import AssistantReply, ToolCall
from agent_harness.tools import Tool, ToolRegistry


class FakeProvider:
    def __init__(self, replies):
        self._replies = replies

    def complete(self, messages, tools):
        return self._replies.pop(0)


def _reg() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="add",
            description="求和",
            parameters={"a": {"type": "integer", "required": True},
                        "b": {"type": "integer", "required": True}},
            func=lambda a, b: str(a + b),
        )
    )
    return reg


def test_pre_tool_use_deny_blocks_tool():
    hooks = Hooks()
    hooks.add_pre_tool_use(
        lambda name, args: HookResult(HookAction.DENY, "[hook] 临时禁止 add")
    )
    provider = FakeProvider(
        [
            AssistantReply(content="算", tool_calls=[ToolCall("t1", "add", '{"a":1,"b":2}')]),
            AssistantReply(content="被拦了"),
        ]
    )
    messages, final = agent_loop("s", "算", provider, _reg(), hooks=hooks)
    assert final == "被拦了"
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert tool_msgs and "临时禁止" in tool_msgs[-1]["content"]


def test_post_tool_use_records_each_call():
    seen = []
    hooks = Hooks()
    hooks.add_post_tool_use(lambda name, args, result: seen.append((name, args)))
    provider = FakeProvider(
        [
            AssistantReply(content="算", tool_calls=[ToolCall("t1", "add", '{"a":3,"b":4}')]),
            AssistantReply(content="7"),
        ]
    )
    _, final = agent_loop("s", "算", provider, _reg(), hooks=hooks)
    assert final == "7"
    assert seen == [("add", {"a": 3, "b": 4})]


def test_pre_turn_hook_injects_context():
    injected = []

    def pt(messages):
        msg = {"role": "user", "content": "提示: 世界的答案可能是 42"}
        messages.insert(1, msg)
        injected.append(len(messages))

    hooks = Hooks()
    hooks.add_pre_turn(pt)
    provider = FakeProvider([AssistantReply(content="好")])
    messages, _ = agent_loop("s", "计算", provider, _reg(), hooks=hooks)
    assert injected[0] == 3


def test_pre_tool_use_exception_is_tolerated():
    hooks = Hooks()

    def bad(name, args):
        raise RuntimeError("hook 崩溃")

    hooks.add_pre_tool_use(bad)
    provider = FakeProvider(
        [
            AssistantReply(content="算", tool_calls=[ToolCall("t1", "add", '{"a":1,"b":1}')]),
            AssistantReply(content="2"),
        ]
    )
    _, final = agent_loop("s", "算", provider, _reg(), hooks=hooks)
    assert final == "2"  # hook 异常不影响工具执行


def test_no_hooks_runs_normally():
    provider = FakeProvider([AssistantReply(content="3", tool_calls=[ToolCall("t", "add", '{"a":1,"b":2}')]),
                             AssistantReply(content="3")])
    _, final = agent_loop("s", "算", provider, _reg(), hooks=None)
    assert final == "3"


def test_pre_tool_use_allow_returns_none_passes():
    hooks = Hooks()
    hooks.add_pre_tool_use(lambda name, args: None)
    provider = FakeProvider([AssistantReply(content="算", tool_calls=[ToolCall("t", "add", '{"a":5,"b":6}')]),
                             AssistantReply(content="11")])
    _, final = agent_loop("s", "算", provider, _reg(), hooks=hooks)
    assert final == "11"