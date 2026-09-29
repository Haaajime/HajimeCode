"""事件总线：图在 worker 线程里跑，订阅者在事件循环里读，所以 publish 必须线程安全。

设计要点：
- publish 可在任意线程调用：序号分配用锁保护，投递用 loop.call_soon_threadsafe。
- stream 先注册订阅者、再读历史，避免"注册与读历史之间"漏事件；已投递的重复事件按
  seq 去重。
- 迟到的订阅者（任务已结束）能从历史里补齐全部事件后正常关闭。
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator
from typing import Any

from .events import TERMINAL_EVENTS, TaskEvent

MAX_HISTORY_PER_TASK = 20_000


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: dict[str, list[TaskEvent]] = {}
        self._seq: dict[str, int] = {}
        self._queues: dict[str, list[asyncio.Queue[TaskEvent]]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """绑定事件循环，供跨线程投递使用。"""
        self._loop = loop

    # ---- 生产 ----
    def publish(self, task_id: str, type_: str, data: dict[str, Any] | None = None) -> TaskEvent:
        with self._lock:
            seq = self._seq.get(task_id, 0) + 1
            self._seq[task_id] = seq
            event = TaskEvent(
                seq=seq,
                task_id=task_id,
                type=type_,
                ts=time.time(),
                data=data or {},
            )
            history = self._history.setdefault(task_id, [])
            history.append(event)
            if len(history) > MAX_HISTORY_PER_TASK:
                del history[: len(history) - MAX_HISTORY_PER_TASK]
            queues = list(self._queues.get(task_id, ()))

        loop = self._loop
        if loop is not None:
            for queue in queues:
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, event)
                except RuntimeError:  # 事件循环已关闭（进程退出中）
                    break
        return event

    # ---- 消费 ----
    def history(self, task_id: str, since: int = 0) -> list[TaskEvent]:
        with self._lock:
            return [event for event in self._history.get(task_id, ()) if event.seq > since]

    def is_finished(self, task_id: str) -> bool:
        return any(event.type in TERMINAL_EVENTS for event in self.history(task_id))

    async def stream(self, task_id: str, since: int = 0) -> AsyncIterator[TaskEvent]:
        queue: asyncio.Queue[TaskEvent] = asyncio.Queue()

        # 先注册订阅者，再读历史：否则两步之间产生的事件会丢失。
        with self._lock:
            self._queues.setdefault(task_id, []).append(queue)
            backlog = [event for event in self._history.get(task_id, ()) if event.seq > since]

        try:
            last = since
            for event in backlog:
                last = max(last, event.seq)
                yield event
            if any(event.type in TERMINAL_EVENTS for event in backlog):
                return

            while True:
                event = await queue.get()
                if event.seq <= last:
                    continue  # 与历史重复
                last = event.seq
                yield event
                if event.type in TERMINAL_EVENTS:
                    return
        finally:
            with self._lock:
                subscribers = self._queues.get(task_id)
                if subscribers and queue in subscribers:
                    subscribers.remove(queue)
