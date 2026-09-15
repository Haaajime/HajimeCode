"""Todo 计划系统:让 Agent 以结构化清单分步推进任务。

机制与 Claude Code 的 todo 类似:
- 提供一个 `update_todo` 工具,模型可用 add/started/complete/revert/abort 维护计划。
- 每个 turn 前由(可选的)PreTurn hook 把当前清单回灌进消息流,保持模型对进度的感知。
- 纯内存态;持久化版本(任务图)归 M14。
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from .hooks import PreTurnFn
from .tools import Tool


class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TodoError(Exception):
    pass


class TodoList:
    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []

    def _check_index(self, index: int) -> None:
        if not 0 <= index < len(self._items):
            raise TodoError(f"任务序号越界: {index} (共 {len(self._items)} 项)")

    def add(self, content: str) -> int:
        self._items.append(
            {"index": len(self._items), "content": content,
             "status": TodoStatus.PENDING}
        )
        return len(self._items) - 1

    def started(self, index: int) -> None:
        self._check_index(index)
        self._items[index]["status"] = TodoStatus.IN_PROGRESS

    def complete(self, index: int) -> None:
        self._check_index(index)
        self._items[index]["status"] = TodoStatus.COMPLETED

    def revert(self, index: int) -> None:
        self._check_index(index)
        self._items[index]["status"] = TodoStatus.PENDING

    def abort(self) -> None:
        self._items.clear()

    def replace(self, index: int, content: str) -> None:
        self._check_index(index)
        self._items[index]["content"] = content

    def to_text(self) -> str:
        if not self._items:
            return "(当前无任务)"
        lines = []
        for it in self._items:
            marker = {
                TodoStatus.PENDING: "[ ]",
                TodoStatus.IN_PROGRESS: "[~]",
                TodoStatus.COMPLETED: "[x]",
            }[it["status"]]
            lines.append(f"  {marker} {it['index']}: {it['content']}")
        return "\n".join(lines)

    def to_hook(self, header: str = "当前任务清单,请据此推进:") -> PreTurnFn:
        def _hook(messages: list[dict[str, Any]]) -> None:
            if not self._items:
                return
            messages.append(
                {"role": "user", "content": f"{header}\n{self.to_text()}"}
            )

        return _hook


def _update_todo(todo: TodoList) -> Tool:
    def _run(action: str, index: int | None = None, content: str | None = None) -> str:
        try:
            if action == "add":
                if not content:
                    return "[tool_error] add 需要 content"
                idx = todo.add(content)
                return f"已添加任务 {idx}: {content}\n{todo.to_text()}"
            if index is None:
                return f"[tool_error] action={action} 需要 index"
            if action == "started":
                todo.started(index)
            elif action == "complete":
                todo.complete(index)
            elif action == "revert":
                todo.revert(index)
            elif action == "replace":
                if not content:
                    return "[tool_error] replace 需要 content"
                todo.replace(index, content)
            else:
                return f"[tool_error] 未知 action: {action}"
            return f"操作成功:{action} {index}\n{todo.to_text()}"
        except TodoError as exc:
            return f"[tool_error] {exc}"

    return Tool(
        name="update_todo",
        description=(
            "维护一个结构化任务清单,用于长任务的分步推进。"
            "action 可选 add(新增,需 content)/started(进行中)/complete(完成)/"
            "revert(回退)/replace(改内容,需 content);对已有任务需给 index。"
        ),
        parameters={
            "action": {"type": "string", "description": "操作类型", "required": True},
            "index": {"type": "integer", "description": "任务序号(除 add 外必填)"},
            "content": {"type": "string", "description": "任务内容(用于 add/replace)"},
        },
        func=_run,
    )


def build_todo_system() -> tuple[TodoList, Tool, PreTurnFn]:
    """组装完整的 todo 机制: 状态容器 + 工具 + 回灌 hook。"""
    tl = TodoList()
    return tl, _update_todo(tl), tl.to_hook()