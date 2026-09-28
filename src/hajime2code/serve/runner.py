"""任务执行器：在 worker 线程里消费图的 stream，翻译事件并发布。

runner 持有"累计状态"（预算、最终 plan/todos/summary），``events.translate`` 只做纯映射。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import Settings
from ..graph.state import add_budget, empty_budget
from ..tools import build_fs_tools
from ..workspace import Workspace
from .bus import EventBus
from .events import extract_state_patch, translate
from .store import TaskStore

STREAM_MODES = ["updates", "messages", "debug"]

# runner 只依赖 `.stream(...)` 这一个鸭子接口。LangGraph 的 CompiledStateGraph.stream
# 是重载 + 大量关键字参数，写成 Protocol 反而无法被满足，因此这里用 Any 做鸭子类型。
GraphFactory = Callable[[Path], Any]


def default_graph_factory(settings: Settings) -> GraphFactory:
    def factory(workspace: Path) -> Any:
        from ..graph.builder import build_default_graph

        ws = Workspace(workspace)
        return build_default_graph(settings, tools=build_fs_tools(ws), workspace=ws)

    return factory


def run_task(
    *,
    task_id: str,
    task: str,
    workspace: Path,
    graph_factory: GraphFactory,
    bus: EventBus,
    store: TaskStore,
    settings: Settings,
) -> None:
    """阻塞执行；由调用方放进 worker 线程（``asyncio.to_thread``）。"""
    bus.publish(task_id, "task.created", {"task": task, "workspace": str(workspace)})
    state: dict[str, Any] = {}
    budget = empty_budget()

    try:
        graph = graph_factory(workspace)
        stream = graph.stream(
            {"task": task},
            config={"recursion_limit": 100 + settings.max_steps * 4},
            stream_mode=STREAM_MODES,
            subgraphs=True,
        )
        for item in stream:
            for translated in translate(item):
                payload = translated.data
                if translated.type == "budget.updated":
                    budget = add_budget(budget, payload["delta"])
                    store.update(task_id, budget=budget)
                    payload = {"total": dict(budget), "delta": payload["delta"]}
                bus.publish(task_id, translated.type, payload)

            patch = extract_state_patch(item)
            if patch is not None:
                patch.pop("budget", None)  # 预算是增量，不能直接覆盖累计值
                patch.pop("__namespace__", None)
                state.update(patch)

    except Exception as exc:  # 任何执行失败都要落成 error 事件，否则前端会一直挂住
        message = f"{type(exc).__name__}: {exc}"
        store.update(task_id, status="failed", summary=message)
        bus.publish(task_id, "error", {"message": message})
        return

    status = str(state.get("status") or "failed")
    summary = str(state.get("summary") or "")
    plan = [str(step) for step in state.get("plan") or []]
    todos = list(state.get("todos") or [])

    store.update(task_id, status=status, summary=summary, plan=plan, todos=todos)
    bus.publish(
        task_id,
        "task.finished",
        {
            "status": status,
            "summary": summary,
            "plan": plan,
            "todos": todos,
            "budget": dict(budget),
        },
    )
