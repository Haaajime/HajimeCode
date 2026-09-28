"""命令行入口：执行一次性任务并输出结论与预算报告。

CLI 走 ``graph.invoke``，是**一次性输出**：token 级流式落在服务端 SSE（见 ``serve/``），
不在终端复现。交互式 REPL 未排期。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .config import Settings
from .graph.builder import build_default_graph
from .graph.state import empty_budget
from .tools import build_fs_tools
from .workspace import Workspace, WorkspaceError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hajime2code",
        description="基于 LangGraph 的编码 Agent 运行时（单任务执行）。",
    )
    parser.add_argument("task", help="要交给 Agent 完成的任务描述")
    parser.add_argument(
        "-w", "--workspace", default=None, help="Agent 可访问的工作目录（默认当前目录）"
    )
    parser.add_argument("--model", default=None, help="覆盖模型名，如 deepseek-chat")
    parser.add_argument("--max-steps", type=int, default=None, help="最大执行步数")
    parser.add_argument("--max-attempts", type=int, default=None, help="最大反思重试轮数")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印规划、待办与预算明细")
    return parser


def _report(state: dict[str, Any], verbose: bool) -> None:
    budget = state.get("budget") or empty_budget()
    print("\n" + "=" * 62)
    print(f"状态：{state.get('status')}")

    if verbose and state.get("plan"):
        print("\n规划：")
        for index, step in enumerate(state["plan"], 1):
            print(f"  {index}. {step}")

    if verbose and state.get("todos"):
        print("\n待办：")
        for todo in state["todos"]:
            print(f"  [{todo['status']}] {todo['content']}")

    print(f"\n结论：{state.get('summary') or '（无）'}")

    total_in = budget["tokens_in"]
    hit = budget["cache_hit_tokens"]
    rate = f"{hit / total_in:.1%}" if total_in else "n/a"
    print("\n预算：")
    print(f"  步数 {budget['steps']} · LLM 调用 {budget['llm_calls']}")
    print(f"  tokens：输入 {total_in} / 输出 {budget['tokens_out']}")
    print(f"  缓存：命中 {hit} / 未命中 {budget['cache_miss_tokens']}（命中率 {rate}）")
    print(f"  成本：¥{budget['cost_cny']:.4f}")
    print("=" * 62)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    settings = Settings()
    overrides: dict[str, Any] = {}
    if args.workspace:
        overrides["workspace"] = Path(args.workspace).expanduser().resolve()
    if args.model:
        overrides["model_name"] = args.model
    if args.max_steps is not None:
        overrides["max_steps"] = args.max_steps
    if args.max_attempts is not None:
        overrides["max_attempts"] = args.max_attempts
    if overrides:
        settings = settings.model_copy(update=overrides)

    try:
        workspace = Workspace(settings.workspace)
    except WorkspaceError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    try:
        settings.require_api_key()
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    print(f"工作区：{workspace.root}")
    print(f"任务：{args.task}")
    print("执行中（CLI 一次性输出；token 级流式见 Web 控制台）…")

    graph = build_default_graph(settings, tools=build_fs_tools(workspace), workspace=workspace)
    try:
        state = graph.invoke(
            {"task": args.task},
            config={"recursion_limit": 100 + settings.max_steps * 4},
        )
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        return 130

    _report(state, args.verbose)
    return 0 if state.get("status") == "done" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
