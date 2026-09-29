"""FastAPI 应用：REST + SSE + 前端静态托管。

长任务模型（对应方案 §4.3）：
POST /api/tasks 立刻返回 task_id（不阻塞），图在 worker 线程里跑，
事件经事件总线推给 GET /api/tasks/{id}/events 的 SSE 订阅者。
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

from ..config import PROJECT_ROOT, Settings
from ..workspace import Workspace, WorkspaceError, is_ignored_name
from .bus import EventBus
from .runner import GraphFactory, default_graph_factory, run_task
from .store import TaskStore
from .stub import STUB_MODEL_ID, STUB_MODEL_LABEL

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"

MAX_BROWSE_ENTRIES = 200

#: 后端接口版本。前端会拿它和自己期望的版本比对 ——
#: 缺了这道握手，旧服务进程会把新前端发出去（StaticFiles 每次请求都从磁盘读），
#: 表现成"模型下拉空白 + 浏览 404"，症状看着莫名其妙。
#: 每次新增/变更前端依赖的接口时都要 +1。
API_VERSION = 2

#: 目录选择器里的快捷预设：样例仓库里几个有代表性的子目录
#: （深嵌套 / 非 ASCII 名 / 含空格名 / 有真实代码）。
SAMPLE_SUBDIRS: tuple[tuple[str, str, str], ...] = (
    ("sample_src_core", "样例 · src/core（核心引擎）", "src/core"),
    ("sample_src_utils", "样例 · src/utils（工具函数）", "src/utils"),
    ("sample_deep", "样例 · docs/deep/nested/more（4 层深嵌套）", "docs/deep/nested/more"),
    ("sample_cjk", "样例 · src/中文模块（非 ASCII 路径）", "src/中文模块"),
    ("sample_spaces", "样例 · dir with spaces（含空格路径）", "dir with spaces"),
)

#: 判断"这里像不像一个项目"，用于目录选择器给出提示。
PROJECT_MARKERS = ("pyproject.toml", "package.json", "AGENTS.md", "CLAUDE.md", "README.md")


class CreateTaskRequest(BaseModel):
    task: str = Field(min_length=1, description="任务描述")
    workspace: str | None = Field(default=None, description="Agent 可访问的工作目录")
    model: str | None = Field(
        default=None,
        description=f"模型名；'{STUB_MODEL_ID}' 为无模型模式，留空用服务端默认",
    )


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

    def _resolve_model(raw: str | None) -> str | None:
        """校验模型名：只接受 null（服务端默认）、无模型模式、或候选列表里的模型。"""
        if raw is None or not raw.strip():
            return None
        name = raw.strip()
        if name == STUB_MODEL_ID or name in resolved_settings.available_models:
            return name
        allowed = [STUB_MODEL_ID, *resolved_settings.available_models]
        raise HTTPException(
            status_code=400, detail=f"未知模型：{name}（可选：{', '.join(allowed)}）"
        )

    def _browse_target(raw: str | None) -> Path:
        """把请求路径解析到浏览根之内的绝对目录；越界即拒绝。

        这是有意设的边界：没有它，接口会变成一个任意读取本机目录的入口。
        """
        root = resolved_settings.resolved_browse_root
        if raw is None or not raw.strip():
            return root
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            target = candidate.resolve()
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"路径无法解析：{raw}") from exc
        if not target.is_relative_to(root):
            raise HTTPException(status_code=400, detail=f"超出可浏览范围：{root}")
        if not target.is_dir():
            raise HTTPException(status_code=400, detail=f"不是目录：{target}")
        return target

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "model": resolved_settings.model_name,
            "api_version": API_VERSION,
        }

    @app.get("/api/models")
    async def list_models() -> dict[str, object]:
        """可选模型：无模型模式 + 服务端配置的候选（能否真实调用取决于是否配了密钥）。"""
        has_key = bool(resolved_settings.api_key.strip())
        entries: list[dict[str, object]] = [
            {
                "id": STUB_MODEL_ID,
                "label": STUB_MODEL_LABEL,
                "kind": "stub",
                "available": True,
            }
        ]
        entries.extend(
            {"id": name, "label": name, "kind": "llm", "available": has_key}
            for name in resolved_settings.available_models
        )
        return {
            "default": resolved_settings.default_model or resolved_settings.model_name,
            "stub_id": STUB_MODEL_ID,
            "has_api_key": has_key,
            "models": entries,
        }

    @app.get("/api/presets")
    async def presets() -> dict[str, object]:
        """目录选择器需要的：浏览根、项目根，以及若干有代表性的工作区预设。"""
        sample = PROJECT_ROOT / "tests" / "fixtures" / "sample_repo"
        workspaces: list[dict[str, str]] = [
            {"key": "project", "label": "Hajime2Code 仓库根", "path": str(PROJECT_ROOT)}
        ]
        if sample.is_dir():
            workspaces.append(
                {"key": "sample_repo", "label": "样例仓库（读取覆盖度基准）", "path": str(sample)}
            )
            for key, label, relative in SAMPLE_SUBDIRS:
                candidate = sample / relative
                if candidate.is_dir():
                    workspaces.append({"key": key, "label": label, "path": str(candidate)})
        return {
            "browse_root": str(resolved_settings.resolved_browse_root),
            "project_root": str(PROJECT_ROOT),
            "workspaces": workspaces,
        }

    @app.get("/api/fs/dirs")
    async def list_dirs(path: str | None = None) -> dict[str, object]:
        """列出可浏览范围内的子目录，供前端目录选择器逐层进入。

        只返回目录（工作区必须是目录）；隐藏目录与构建产物目录被隐藏，
        但会把隐藏数量如实报出，不制造"这里什么都没有"的错觉。
        """
        target = _browse_target(path)
        root = resolved_settings.resolved_browse_root

        directories: list[dict[str, str]] = []
        hidden = 0
        for entry in sorted(target.iterdir(), key=lambda item: item.name):
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            if entry.name.startswith(".") or is_ignored_name(entry.name):
                hidden += 1
                continue
            directories.append({"name": entry.name, "path": str(entry)})

        markers = [name for name in PROJECT_MARKERS if (target / name).is_file()]
        return {
            "browse_root": str(root),
            "path": str(target),
            "relative": "." if target == root else target.relative_to(root).as_posix(),
            "parent": None if target == root else str(target.parent),
            "dirs": directories[:MAX_BROWSE_ENTRIES],
            "truncated": len(directories) > MAX_BROWSE_ENTRIES,
            "hidden_count": hidden,
            "markers": markers,
        }

    @app.post("/api/tasks", status_code=201)
    async def create_task(payload: CreateTaskRequest, request: Request) -> dict[str, str]:
        workspace = _resolve_workspace(payload.workspace)
        model = _resolve_model(payload.model)
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
            model=model,
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
