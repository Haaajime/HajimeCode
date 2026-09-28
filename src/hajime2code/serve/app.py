"""FastAPI 应用：REST + SSE + 前端静态托管。

长任务模型（对应方案 §4.3）：
``POST /api/tasks`` 立刻返回 ``task_id``（不阻塞），图在 worker 线程里跑，
事件经事件总线推给 ``GET /api/tasks/{id}/events`` 的 SSE 订阅者。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..config import Settings
from ..workspace import Workspace, WorkspaceError
from .bus import EventBus
from .runner import GraphFactory, default_graph_factory, run_task
from .store import TaskStore

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


class CreateTaskRequest(BaseModel):
    task: str = Field(min_length=1, description="任务描述")
    workspace: str | None = Field(default=None, description="Agent 可访问的工作目录")


def create_app(
    *,
    settings: Settings | None = None,
    graph_factory: GraphFactory | None = None,
    bus: EventBus | None = None,
    store: TaskStore | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    resolved_bus = bus or EventBus()
    resolved_store = store or TaskStore()
    factory = graph_factory or default_graph_factory(resolved_settings)

    background: set[asyncio.Task[None]] = set()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        resolved_bus.bind_loop(asyncio.get_running_loop())
        yield

    app = FastAPI(title="Hajime2Code", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.bus = resolved_bus
    app.state.store = resolved_store
    app.state.graph_factory = factory

    def _resolve_workspace(raw: str | None) -> Workspace:
        target = Path(raw).expanduser() if raw else resolved_settings.workspace
        try:
            return Workspace(target)
        except WorkspaceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "model": resolved_settings.model_name}

    @app.post("/api/tasks", status_code=201)
    async def create_task(payload: CreateTaskRequest, request: Request) -> dict[str, str]:
        workspace = _resolve_workspace(payload.workspace)
        resolved_bus.bind_loop(asyncio.get_running_loop())
        record = resolved_store.create(task=payload.task, workspace=str(workspace.root))

        coro = asyncio.to_thread(
            run_task,
            task_id=record.id,
            task=payload.task,
            workspace=workspace.root,
            graph_factory=factory,
            bus=resolved_bus,
            store=resolved_store,
            settings=resolved_settings,
        )
        handle = asyncio.create_task(coro)
        background.add(handle)
        handle.add_done_callback(background.discard)
        request.app.state.background = background

        return {"task_id": record.id}

    @app.get("/api/tasks")
    async def list_tasks() -> list[dict[str, object]]:
        return [record.to_dict() for record in resolved_store.list()]

    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: str) -> dict[str, object]:
        record = resolved_store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        return record.to_dict()

    @app.get("/api/tasks/{task_id}/events")
    async def stream_events(
        task_id: str,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> EventSourceResponse:
        if resolved_store.get(task_id) is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        try:
            since = int(last_event_id or 0)
        except ValueError:
            since = 0

        async def publisher() -> AsyncIterator[dict[str, str]]:
            async for event in resolved_bus.stream(task_id, since=since):
                yield event.to_sse()

        return EventSourceResponse(publisher())

    @app.get("/api/tasks/{task_id}/events/history")
    async def event_history(task_id: str) -> list[dict[str, object]]:
        """非流式读取（便于测试与调试）。"""
        if resolved_store.get(task_id) is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        return [event.model_dump() for event in resolved_bus.history(task_id)]

    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

        @app.get("/task/{task_id}")
        async def spa_route(task_id: str) -> FileResponse:
            return FileResponse(WEB_DIST / "index.html")

    return app
