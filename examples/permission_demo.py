"""权限层离线演示 —— 不调用真实 API,展示 allow/ask/deny 三种路径。

运行:
    uv run python examples/permission_demo.py
"""
from __future__ import annotations

from agent_harness.permissions import Decision, PermissionManager, PermissionRule


def main() -> None:
    # 场景1: 命令白名单 —— 只放行 pytest/git status,其余默认拒绝
    pm_whitelist = PermissionManager(
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
    print("== 场景1: 白名单(fail-closed) ==")
    for cmd in ["pytest -q", "git status", "rm -rf /"]:
        ok, reason = pm_whitelist.resolve("run_cmd", {"cmd": cmd})
        print(f"  {cmd!r:14s} -> {'ALLOW' if ok else 'DENY'}"
              + ("" if ok else f" ({reason})"))

    # 场景2: ask + 审批(approver 放行)
    pm_ask = PermissionManager(
        rules=[PermissionRule(strategy=Decision.ASK, tool_name="run_cmd")],
        default=Decision.DENY,
        approver=lambda name, args: True,
    )
    print("== 场景2: ask + 审批(放行) ==")
    ok2, reason2 = pm_ask.resolve("run_cmd", {"cmd": "git pull"})
    print(f"  {'git pull':14s} -> {'ALLOW' if ok2 else 'DENY'} ({reason2 or '审批通过'})")


if __name__ == "__main__":
    main()