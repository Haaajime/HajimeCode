"""权限层单测 —— 全部离线 mock,零 API 消耗。"""
from __future__ import annotations

from typing import Any

import pytest

from agent_harness.loop import agent_loop
from agent_harness.permissions import (
    Decision,
    PermissionManager,
    PermissionRule,
)
from agent_harness.providers import AssistantReply, ToolCall
from agent_harness.tools import Tool, ToolRegistry


class FakeProvider:
    def __init__(self, replies):
        self._replies = replies

    def complete(self, messages, tools):
        return self._replies.pop(0)


def _reg_with_tools() -> ToolRegistry:
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
    reg.register(
        Tool(
            name="run_cmd",
            description="执行命令",
            parameters={"cmd": {"type": "string", "required": True}},
            func=lambda cmd: f"ran:{cmd}",
        )
    )
    return reg


def test_default_deny_fail_closed():
    """未命中任何规则时默认拒绝(fail-closed)。"""
    pm = PermissionManager(rules=[], default=Decision.DENY)
    ok, reason = pm.resolve("run_cmd", {"cmd": "rm -rf /"})
    assert not ok
    assert "permission_denied" in reason


def test_allow_rule_lets_dispatch_run():
    """放行 add: 工具真实被调用,模型拿到结果后正常结束。"""
    pm = PermissionManager(
        rules=[PermissionRule(strategy=Decision.ALLOW, tool_name="add")],
        default=Decision.DENY,
    )
    provider = FakeProvider(
        [
            AssistantReply(
                content="计算",
                tool_calls=[ToolCall("t1", "add", '{"a":2,"b":3}')],
            ),
            AssistantReply(content="5"),
        ]
    )
    _, final = agent_loop("sys", "2+3?",
                          provider, _reg_with_tools(), permissions=pm)
    assert final == "5"


def test_deny_rule_blocks_tool_and_returns_denial():
    """拒绝: 工具不执行,以 permission_denied 作 tool_result 回传,再让模型给出结论。"""
    pm = PermissionManager(
        rules=[PermissionRule(strategy=Decision.DENY, tool_name="run_cmd")],
        default=Decision.DENY,
    )
    provider = FakeProvider(
        [
            AssistantReply(
                content="执行",
                tool_calls=[ToolCall("t2", "run_cmd", '{"cmd":"rm -rf /"}')],
            ),
            AssistantReply(content="被阻止,我不执行"),
        ]
    )
    messages, final = agent_loop("sys", "删文件", provider, _reg_with_tools(), permissions=pm)
    assert final == "被阻止,我不执行"
    denied = [m for m in messages if m["role"] == "tool"]
    assert denied and "permission_denied" in denied[-1]["content"]
    # run_cmd 的函数体未被调用(没有 `ran:` 前缀)
    assert all("ran:" not in m["content"] for m in denied)


def test_ask_with_denying_approver_blocks():
    """ask 命中 + approver 拒绝 → 不放行。"""
    pm = PermissionManager(
        rules=[PermissionRule(strategy=Decision.ASK, tool_name="run_cmd")],
        default=Decision.DENY,
        approver=lambda name, args: False,
    )
    ok, reason = pm.resolve("run_cmd", {"cmd": "id"})
    assert not ok
    assert "审批拒绝" in reason


def test_ask_with_approving_approver_allows():
    """ask 命中 + approver 放行 → 执行。"""
    pm = PermissionManager(
        rules=[PermissionRule(strategy=Decision.ASK, tool_name="run_cmd")],
        default=Decision.DENY,
        approver=lambda name, args: True,
    )
    ok, _ = pm.resolve("run_cmd", {"cmd": "ls"})
    assert ok


def test_command_pattern_whitelist():
    """bash 式: 只放行允许 safe 前缀、拒绝危险命令。"""
    pm = PermissionManager(
        rules=[
            PermissionRule(
                strategy=Decision.ALLOW,
                tool_name="run_cmd",
                command_pattern=r"^(pytest|git status)\b",
                reason="命令白名单",
            )
        ],
        default=Decision.DENY,
    )
    assert pm.resolve("run_cmd", {"cmd": "pytest -q"})[0]
    assert pm.resolve("run_cmd", {"cmd": "git status"})[0]
    assert not pm.resolve("run_cmd", {"cmd": "rm -rf /"})[0]