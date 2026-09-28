"""任务记录存储（内存实现）。

worker 线程会更新状态、事件循环会读，所以所有访问走同一把锁。
持久化（Postgres）留到 W4 与 checkpointer 一起做。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..graph.state import Budget, empty_budget


@dataclass
class TaskRecord:
    id: str
    task: str
    workspace: str
    created_at: float
    status: str = "running"
    summary: str = ""
    plan: list[str] = field(default_factory=list)
    todos: list[dict[str, Any]] = field(default_factory=list)
    budget: Budget = field(default_factory=empty_budget)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "workspace": self.workspace,
            "created_at": self.created_at,
            "status": self.status,
            "summary": self.summary,
            "plan": self.plan,
            "todos": self.todos,
            "budget": dict(self.budget),
        }


class TaskStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, TaskRecord] = {}

    def create(self, task: str, workspace: str) -> TaskRecord:
        record = TaskRecord(
            id=uuid.uuid4().hex[:12],
            task=task,
            workspace=workspace,
            created_at=time.time(),
        )
        with self._lock:
            self._records[record.id] = record
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._records.get(task_id)

    def list(self) -> list[TaskRecord]:
        with self._lock:
            records = list(self._records.values())
        return sorted(records, key=lambda r: r.created_at, reverse=True)

    def update(self, task_id: str, **fields: Any) -> None:
        with self._lock:
            record = self._records.get(task_id)
            if record is None:
                return
            for key, value in fields.items():
                setattr(record, key, value)
