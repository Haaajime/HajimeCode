"""事件协议：把 LangGraph 的流式输出翻译成前端可消费的事件。

LangGraph 的 stream 输出形状（已实测，langgraph 1.2.12）：

- 不传 subgraphs：(mode, data)
- 传 subgraphs=True：(namespace, mode, data)
- updates：{节点名: 该节点返回的增量}
- messages：(AIMessageChunk, metadata)，metadata 含 langgraph_node
- debug：{"type": "task" | "task_result" | "checkpoint", "step": int, "payload": {...}}

translate 只做纯映射（不持有状态），预算累计由 runner 负责。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from pydantic import BaseModel

EventType = Literal[
    "task.created",
    "node.started",
    "node.finished",
    "assistant.message",
    "llm.token",
    "tool.started",
    "tool.finished",
    "budget.updated",
    "approval.required",
    "task.finished",
    "error",
]

TERMINAL_EVENTS: frozenset[str] = frozenset({"task.finished", "error"})

PREVIEW_CHARS = 300


class TaskEvent(BaseModel):
    """推送与落盘的最小事件单元。seq 单调递增，用于 SSE 的 Last-Event-ID 续传。"""

    seq: int
    task_id: str
    type: str
    ts: float
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> dict[str, str]:
        return {
            "event": self.type,
            "id": str(self.seq),
            "data": self.model_dump_json(),
        }


@dataclass(frozen=True)
class Translated:
    type: str
    data: dict[str, Any]


def normalize(item: Any) -> tuple[tuple[str, ...], str, Any]:
    """把 2 元组 / 3 元组的流条目统一成 (namespace, mode, data)。"""
    if isinstance(item, tuple):
        if len(item) == 3:
            namespace, mode, data = item
            return tuple(namespace), str(mode), data
        if len(item) == 2:
            mode, data = item
            return (), str(mode), data
    return (), "unknown", item


def _preview(text: Any, limit: int = PREVIEW_CHARS) -> str:
    value = text if isinstance(text, str) else str(text)
    return value if len(value) <= limit else value[:limit] + "…"


def _translate_debug(data: dict[str, Any]) -> list[Translated]:
    kind = data.get("type")
    payload = data.get("payload") or {}
    node = payload.get("name") or "?"
    step = data.get("step")
    if kind == "task":
        return [Translated("node.started", {"node": node, "step": step})]
    if kind == "task_result":
        return [
            Translated(
                "node.finished",
                {"node": node, "step": step, "error": payload.get("error")},
            )
        ]
    return []


def _translate_updates(data: dict[str, Any]) -> list[Translated]:
    out: list[Translated] = []
    for node, patch in data.items():
        if not isinstance(patch, dict):
            continue
        if isinstance(patch.get("budget"), dict):
            out.append(Translated("budget.updated", {"delta": patch["budget"]}))
        for message in patch.get("messages") or []:
            if isinstance(message, AIMessage):
                for call in message.tool_calls or []:
                    out.append(
                        Translated(
                            "tool.started",
                            {
                                "node": node,
                                "name": call.get("name", "?"),
                                "args": call.get("args") or {},
                            },
                        )
                    )
                text = message.content
                if isinstance(text, str) and text.strip():
                    out.append(Translated("assistant.message", {"node": node, "text": text}))
            elif isinstance(message, ToolMessage):
                ok = getattr(message, "status", "success") != "error"
                out.append(
                    Translated(
                        "tool.finished",
                        {
                            "node": node,
                            "name": getattr(message, "name", "?"),
                            "ok": ok,
                            "preview": _preview(message.content),
                        },
                    )
                )
    return out


def _translate_messages(data: Any) -> list[Translated]:
    if not isinstance(data, tuple) or len(data) != 2:
        return []
    chunk, metadata = data
    # messages 模式会把节点写入的普通消息也当成"消息"流出（例如 intake 写入的
    # HumanMessage）。只有 AIMessageChunk 才是真正的模型 token 流，否则会把用户
    # 自己的输入误报成模型输出。
    if not isinstance(chunk, AIMessageChunk):
        return []
    content = chunk.content
    if not isinstance(content, str) or not content:
        return []
    node = (metadata or {}).get("langgraph_node", "?")
    return [Translated("llm.token", {"node": node, "text": content})]


def translate(item: Any) -> list[Translated]:
    """把一个流条目翻译成零到多个事件。纯函数，便于离线单测。"""
    _namespace, mode, data = normalize(item)
    if mode == "debug" and isinstance(data, dict):
        return _translate_debug(data)
    if mode == "updates" and isinstance(data, dict):
        return _translate_updates(data)
    if mode == "messages":
        return _translate_messages(data)
    return []


def extract_state_patch(item: Any) -> dict[str, Any] | None:
    """取出 updates 条目里的节点输出，供 runner 合并成最终状态。"""
    namespace, mode, data = normalize(item)
    if mode != "updates" or not isinstance(data, dict):
        return None
    patch: dict[str, Any] = {}
    for _node, value in data.items():
        if isinstance(value, dict):
            patch.update(value)
    patch["__namespace__"] = list(namespace)
    return patch
