"""finalize：收束任务，产出最终结论。"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from ..state import AgentState, NodeFn


def _last_ai_text(state: AgentState) -> str:
    for message in reversed(list(state.get("messages") or [])):
        if isinstance(message, AIMessage) and getattr(message, "content", None):
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""


def make_finalize_node() -> NodeFn:
    def finalize(state: AgentState) -> dict[str, Any]:
        status = state.get("status") or "failed"
        summary = state.get("summary") or _last_ai_text(state) or "（未产出结论）"
        return {"status": "done" if status == "running" else status, "summary": summary}

    return finalize
