"""intake：把用户任务载入状态，并初始化流程控制字段。"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from ..state import AgentState, NodeFn


def make_intake_node() -> NodeFn:
    def intake(state: AgentState) -> dict[str, Any]:
        return {
            "status": "running",
            "attempts": 0,
            "todos": [],
            "findings": [],
            "messages": [HumanMessage(content=state.get("task", ""))],
        }

    return intake
