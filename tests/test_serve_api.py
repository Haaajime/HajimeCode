"""API 层测试：用 httpx ASGITransport 直接打 ASGI 应用，不启动真实服务。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from hajime2code.config import Settings
from hajime2code.serve.app import create_app


class StubGraph:
    def stream(self, input: Any, config: Any = None, **kwargs: Any) -> Iterator[Any]:
        yield ((), "debug", {"step": 1, "type": "task", "payload": {"name": "intake"}})
        yield ((), "updates", {"plan": {"budget": {"llm_calls": 1, "tokens_in": 42}}})
        yield ((), "updates", {"finalize": {"status": "done", "summary": "桩任务完成"}})


def _client(settings: Settings) -> httpx.AsyncClient:
    app = create_app(settings=settings, graph_factory=lambda _ws: StubGraph())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


async def _wait_finished(client: httpx.AsyncClient, task_id: str) -> list[dict[str, Any]]:
    for _ in range(100):
        response = await client.get(f"/api/tasks/{task_id}/events/history")
        events: list[dict[str, Any]] = response.json()
        if events and events[-1]["type"] in {"task.finished", "error"}:
            return events
        await asyncio.sleep(0.02)
    raise AssertionError("任务未在预期时间内结束")


async def test_health(settings: Settings) -> None:
    async with _client(settings) as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_create_task_returns_id_immediately(settings: Settings) -> None:
    async with _client(settings) as client:
        response = await client.post("/api/tasks", json={"task": "看看项目结构"})
        assert response.status_code == 201
        task_id = response.json()["task_id"]
        assert task_id

        events = await _wait_finished(client, task_id)
        kinds = [event["type"] for event in events]
        assert kinds[0] == "task.created"
        assert "budget.updated" in kinds
        assert kinds[-1] == "task.finished"
        assert events[-1]["data"]["summary"] == "桩任务完成"


async def test_task_is_listed_and_fetchable(settings: Settings) -> None:
    async with _client(settings) as client:
        task_id = (await client.post("/api/tasks", json={"task": "t"})).json()["task_id"]
        await _wait_finished(client, task_id)

        listed = (await client.get("/api/tasks")).json()
        assert [item["id"] for item in listed] == [task_id]

        detail = (await client.get(f"/api/tasks/{task_id}")).json()
        assert detail["status"] == "done"
        assert detail["summary"] == "桩任务完成"


async def test_unknown_task_is_404(settings: Settings) -> None:
    async with _client(settings) as client:
        assert (await client.get("/api/tasks/nope")).status_code == 404
        assert (await client.get("/api/tasks/nope/events")).status_code == 404


async def test_invalid_workspace_is_400(settings: Settings, tmp_path: Path) -> None:
    async with _client(settings) as client:
        response = await client.post(
            "/api/tasks", json={"task": "t", "workspace": str(tmp_path / "不存在")}
        )
    assert response.status_code == 400
    assert "不是目录" in response.json()["detail"]


async def test_empty_task_is_rejected(settings: Settings) -> None:
    async with _client(settings) as client:
        assert (await client.post("/api/tasks", json={"task": ""})).status_code == 422


@pytest.mark.parametrize("bad_cursor", ["abc", ""])
async def test_bad_last_event_id_falls_back_to_zero(settings: Settings, bad_cursor: str) -> None:
    async with _client(settings) as client:
        task_id = (await client.post("/api/tasks", json={"task": "t"})).json()["task_id"]
        await _wait_finished(client, task_id)
        response = await client.get(
            f"/api/tasks/{task_id}/events/history", headers={"Last-Event-ID": bad_cursor}
        )
    assert response.status_code == 200
