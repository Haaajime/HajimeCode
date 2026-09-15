"""命令行运行入口:让 Agent 带上内置工具回答一个提示词。

用法:
    agent-harness "计算 3+5 的结果"
    agent-harness "请用 add 工具计算 42+99 的和"
"""
from __future__ import annotations

import sys

from .config import get_settings
from .loop import agent_loop
from .providers import OpenAICompatibleProvider
from .tools import default_registry

SYSTEM = (
    "你是运行在 Agent 框架中的助手。你可以调用给定的工具完成任务。"
    "当需要计算或查询时,应使用对应工具,而不是凭记忆作答。"
)


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: agent-harness \"你的提示词\"")
        return 2
    prompt = " ".join(sys.argv[1:])

    registry = default_registry()
    provider = OpenAICompatibleProvider(get_settings())
    _, final = agent_loop(SYSTEM, prompt, provider, registry)

    print("=" * 40)
    print("最终答复:")
    print(final or "(无文本输出)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())