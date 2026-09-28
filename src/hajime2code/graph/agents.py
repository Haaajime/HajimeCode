"""``act`` 节点内部的 ReAct 子图工厂。

双层图设计的下半层：主图（``builder.py``）管图级控制流，本模块负责"一步之内怎么做完"。
复用官方 ``create_agent``，从而直接获得 LangChain 1.0 的 middleware 生态
（todo / summarization / human-in-the-loop / shell-tool 等）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from ..prompts import AGENT_SYSTEM


def build_react_agent(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    *,
    system_prompt: str = AGENT_SYSTEM,
    middleware: Sequence[Any] = (),
    checkpointer: Any | None = None,
) -> CompiledStateGraph:
    """装配节点内部的 ReAct 子图（官方 harness + middleware）。"""
    return create_agent(
        model,
        list(tools),
        system_prompt=system_prompt,
        middleware=list(middleware),
        checkpointer=checkpointer,
    )
