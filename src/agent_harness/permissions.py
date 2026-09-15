"""权限治理层(s03): 在工具执行前做 allow/ask/deny 判定。

设计要点:
- match-first: 规则按顺序匹配,命中即返回其策略;全部未命中 → 默认策略。
- 默认 DENY(fail-closed),保证新增工具默认不可执行,须显式放行。
- ask 需 approver 回调(CLI 用交互式;测试/无头场景注入确定性回调)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

# 批准回调: 返回 True 放行、False 拒绝
Approver = Callable[[str, dict[str, Any]], bool]


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class PermissionRule:
    """一条权限规则。

    - tool_name: 为空表示匹配所有工具;否则精确匹配工具名。
    - command_pattern: 对参数中首个字符串参数做正则匹配,用于 bash 等命令工具的白名单。
    - strategy: 命中后的策略。
    - reason: 拒绝/询问时回传给模型的说明。
    """
    strategy: Decision
    tool_name: str | None = None
    command_pattern: str | None = None
    reason: str = "未授权"

    def matches(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        if self.tool_name is not None and self.tool_name != tool_name:
            return False
        if self.command_pattern is not None:
            cmd = next(
                (v for v in arguments.values() if isinstance(v, str)), ""
            )
            if self.command_pattern and not re.search(self.command_pattern, cmd):
                return False
        return True


class PermissionManager:
    def __init__(
        self,
        rules: list[PermissionRule] | None = None,
        default: Decision = Decision.DENY,
        approver: Approver | None = None,
    ) -> None:
        self._rules = list(rules or [])
        self._default = default
        self.approver = approver

    def decide(self, tool_name: str, arguments: dict[str, Any]) -> tuple[Decision, str]:
        for rule in self._rules:
            if rule.matches(tool_name, arguments):
                return rule.strategy, rule.reason
        return self._default, "未命中任何放行规则"

    def resolve(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[bool, str]:
        """返回 (是否放行, 拒绝说明)。ask 由 approver 决定。"""
        decision, reason = self.decide(tool_name, arguments)
        if decision is Decision.ALLOW:
            return True, ""
        if decision is Decision.DENY:
            return False, f"[permission_denied] 调用 {tool_name} 被拒绝: {reason}"

        # ASK
        if self.approver is None:
            return (
                False,
                f"[permission_denied] 调用 {tool_name} 需人工审批,但未配置 approver",
            )
        if self.approver(tool_name, arguments):
            return True, ""
        return False, f"[permission_denied] 调用 {tool_name} 被审批拒绝"


def y_n_approver(prompt: str) -> Approver:
    """CLI 交互式 approver,根据输入 y/n 放行/拒绝。"""

    def _ask(tool_name: str, arguments: dict[str, Any]) -> bool:
        while True:
            ans = input(f"{prompt} 允许调用 {tool_name}? [y/n] ").strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no"):
                return False

    return _ask