"""Hooks 事件钩子:在 Agent 生命周期节点上挂用户回调,用于观测/拦截/注料。

与权限层正交:
- PermissionManager 是"规则式、fail-closed"的强制安全边界。
- Hooks 是"用户编排"的扩展点:例如记录每次工具调用、临时拦截某个命令、
  在每个 turn 前注入一条上下文消息。

约定:
- PreToolUse 回调返回 None 表示放行;返回 HookResult(action=DENY) 可拦截。
- 回调抛出的异常会被捕获并转为提示信息,不应让整个循环崩溃;
  安全强制仍交给 PermissionManager,不依赖 Hook。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

PreToolUseFn = Callable[[str, dict[str, Any]], "HookResult | None"]
PostToolUseFn = Callable[[str, dict[str, Any], str], None]
PreTurnFn = Callable[[list[dict[str, Any]]], None]


class HookAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class HookResult:
    action: HookAction = HookAction.ALLOW
    message: str = ""


@dataclass
class Hooks:
    """按事件类型聚合回调。未添加的类型为空列表。"""

    pre_tool_use: list[PreToolUseFn] = field(default_factory=list)
    post_tool_use: list[PostToolUseFn] = field(default_factory=list)
    pre_turn: list[PreTurnFn] = field(default_factory=list)

    def add_pre_tool_use(self, fn: PreToolUseFn) -> None:
        self.pre_tool_use.append(fn)

    def add_post_tool_use(self, fn: PostToolUseFn) -> None:
        self.post_tool_use.append(fn)

    def add_pre_turn(self, fn: PreTurnFn) -> None:
        self.pre_turn.append(fn)


class HookError(Exception):
    """代表某个 Hook 回调自身抛出的错误。"""


def run_pre_tool_use(hooks: Hooks, name: str, args: dict[str, Any]) -> HookResult | None:
    """按序执行 PreToolUse 回调。任一 DENY 即整体拦截;回调异常被捕获并作为 ALLOW 继续。"""
    for fn in hooks.pre_tool_use:
        try:
            res = fn(name, args)
        except Exception as exc:  # noqa: BLE001 —— 观测类代码容错,安全由权限层把关
            res = HookResult(
                HookAction.ALLOW, f"[hook] PreToolUse 回调异常已忽略: {exc}"
            )
        if res is not None and res.action == HookAction.DENY:
            return res
    return None


def run_post_tool_use(hooks: Hooks, name: str, args: dict[str, Any], result: str) -> None:
    for fn in hooks.post_tool_use:
        try:
            fn(name, args, result)
        except Exception:  # noqa: BLE001
            continue


def run_pre_turn(hooks: Hooks, messages: list[dict[str, Any]]) -> None:
    """在每个模型调用 turn 之前执行;回调可原地修改 messages 注入内容。"""
    for fn in hooks.pre_turn:
        try:
            fn(messages)
        except Exception:  # noqa: BLE001
            continue