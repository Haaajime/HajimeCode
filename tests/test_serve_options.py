"""服务端可选项：模型列表 / 目录预设 / 目录浏览（含边界） / 无模型模式。

重点验证三件事：
1. **无模型模式在没有任何 API 密钥时也能跑通**，且预算为零 —— 这是它存在的意义。
2. 目录浏览**不能越过浏览根**，否则接口会变成任意读取本机目录的入口。
3. 非法模型名要被拒绝，而不是静默回退到默认模型（静默回退会让用户以为跑的是自己选的模型）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest

from hajime2code.config import Settings
from hajime2code.serve.app import API_VERSION, create_app
from hajime2code.serve.stub import STUB_MODEL_ID, _keyword


def _settings(root: Path, **overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "api_key": "",
        "base_url": "http://127.0.0.1:1",
        "model_name": "test-model",
        "workspace": root,
        "browse_root": root,
        "max_steps": 6,
    }
    base.update(overrides)
    return Settings(**base)


def _client(settings: Settings) -> httpx.AsyncClient:
    app = create_app(settings=settings)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


async def _wait_finished(client: httpx.AsyncClient, task_id: str) -> list[dict[str, Any]]:
    for _ in range(200):
        response = await client.get(f"/api/tasks/{task_id}/events/history")
        events: list[dict[str, Any]] = response.json()
        if events and events[-1]["type"] in {"task.finished", "error"}:
            return events
        await asyncio.sleep(0.02)
    raise AssertionError("任务未在预期时间内结束")


def _assistant_text(events: list[dict[str, Any]]) -> str:
    """无模型模式下的"模型输出"通过 assistant.message 事件下发（不是 task.finished.summary，
    后者来自 judge 的验收结论）。"""
    return "\n".join(
        str(event["data"].get("text", ""))
        for event in events
        if event["type"] == "assistant.message"
    )


# ---------------------------------------------------------------- 模型列表


async def test_health_exposes_api_version(tmp_path: Path) -> None:
    """版本握手：前端靠它判断服务端是不是旧进程，缺了就会变成莫名其妙的空白/404。"""
    async with _client(_settings(tmp_path)) as client:
        payload = (await client.get("/api/health")).json()
    assert payload["api_version"] == API_VERSION
    assert isinstance(payload["api_version"], int)


async def test_models_lists_stub_first_and_flags_key_availability(tmp_path: Path) -> None:
    async with _client(_settings(tmp_path)) as client:
        payload = (await client.get("/api/models")).json()

    assert payload["stub_id"] == STUB_MODEL_ID
    assert payload["has_api_key"] is False
    first = payload["models"][0]
    assert first["id"] == STUB_MODEL_ID
    assert first["available"] is True, "无模型模式不依赖密钥，必须始终可用"

    llm_entries = [item for item in payload["models"] if item["kind"] == "llm"]
    assert llm_entries, "应列出配置的模型候选"
    assert all(item["available"] is False for item in llm_entries), "没有密钥时模型不可用"
    assert payload["default"] in {item["id"] for item in llm_entries}


async def test_models_marks_llm_available_when_key_present(tmp_path: Path) -> None:
    async with _client(_settings(tmp_path, api_key="sk-test")) as client:
        payload = (await client.get("/api/models")).json()
    assert payload["has_api_key"] is True
    assert all(item["available"] for item in payload["models"] if item["kind"] == "llm")


async def test_custom_model_choices_are_exposed(tmp_path: Path) -> None:
    settings = _settings(tmp_path, model_choices="alpha,beta")
    async with _client(settings) as client:
        payload = (await client.get("/api/models")).json()
    ids = {item["id"] for item in payload["models"]}
    assert {"test-model", "alpha", "beta"} <= ids


async def test_default_model_falls_back_to_configured_model(tmp_path: Path) -> None:
    async with _client(_settings(tmp_path)) as client:
        payload = (await client.get("/api/models")).json()
    assert payload["default"] == "test-model"


async def test_default_model_can_be_pinned_to_stub(tmp_path: Path) -> None:
    """把初始选中设成无模型模式 —— 避免"手一抖就产生真实费用"。"""
    settings = _settings(tmp_path, default_model=STUB_MODEL_ID)
    async with _client(settings) as client:
        payload = (await client.get("/api/models")).json()
    assert payload["default"] == STUB_MODEL_ID


# ---------------------------------------------------------------- 预设


async def test_presets_expose_sample_repo_and_its_subdirs(tmp_path: Path) -> None:
    async with _client(_settings(tmp_path)) as client:
        payload = (await client.get("/api/presets")).json()

    keys = {item["key"] for item in payload["workspaces"]}
    assert "project" in keys
    assert "sample_repo" in keys

    # 子文件夹场景：深嵌套 / 非 ASCII / 含空格 / 真实代码目录
    assert {"sample_deep", "sample_cjk", "sample_spaces", "sample_src_core"} <= keys

    sample = next(item for item in payload["workspaces"] if item["key"] == "sample_repo")
    assert Path(sample["path"]).is_dir()
    for item in payload["workspaces"]:
        assert Path(item["path"]).is_dir(), f"{item['key']} 的路径不存在"


# ---------------------------------------------------------------- 目录浏览


async def test_browse_lists_subdirectories_only(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")

    async with _client(_settings(tmp_path)) as client:
        payload = (await client.get("/api/fs/dirs")).json()

    assert [item["name"] for item in payload["dirs"]] == ["alpha", "beta"]
    assert payload["parent"] is None
    assert payload["relative"] == "."


async def test_browse_descends_and_reports_parent(tmp_path: Path) -> None:
    (tmp_path / "alpha" / "inner").mkdir(parents=True)

    async with _client(_settings(tmp_path)) as client:
        payload = (await client.get("/api/fs/dirs", params={"path": "alpha"})).json()

    assert payload["relative"] == "alpha"
    assert [item["name"] for item in payload["dirs"]] == ["inner"]
    assert Path(payload["parent"]) == tmp_path


async def test_browse_hides_noise_but_reports_the_count(tmp_path: Path) -> None:
    (tmp_path / "keep").mkdir()
    for noise in (".git", "node_modules", "__pycache__"):
        (tmp_path / noise).mkdir()

    async with _client(_settings(tmp_path)) as client:
        payload = (await client.get("/api/fs/dirs")).json()

    assert [item["name"] for item in payload["dirs"]] == ["keep"]
    assert payload["hidden_count"] == 3, "隐藏了多少必须如实报出，不能假装不存在"


async def test_browse_detects_project_markers(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")

    async with _client(_settings(tmp_path)) as client:
        payload = (await client.get("/api/fs/dirs")).json()

    assert set(payload["markers"]) == {"pyproject.toml", "README.md"}


@pytest.mark.parametrize("escape", ["/etc", "../..", "/tmp"])
async def test_browse_refuses_to_leave_the_root(tmp_path: Path, escape: str) -> None:
    """边界是这接口的安全底线：没有它就是一个任意读取本机目录的入口。"""
    async with _client(_settings(tmp_path)) as client:
        response = await client.get("/api/fs/dirs", params={"path": escape})
    assert response.status_code == 400
    assert "超出可浏览范围" in response.json()["detail"]


async def test_workspace_may_live_outside_the_browse_root(tmp_path: Path) -> None:
    """关键区别：**浏览有范围，工作目录没有**。

    直接给绝对路径可以指向浏览范围之外的目录 —— 这既是产品需要（要能对任意仓库干活），
    也说明浏览边界的作用是"别在界面上瞎逛"，而不是"禁止访问"。
    """
    inside = tmp_path / "browse"
    outside = tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()

    settings = _settings(inside, browse_root=inside)
    async with _client(settings) as client:
        blocked = await client.get("/api/fs/dirs", params={"path": str(outside)})
        assert blocked.status_code == 400, "浏览范围外不给列举"

        accepted = await client.post(
            "/api/tasks",
            json={"task": "x", "workspace": str(outside), "model": STUB_MODEL_ID},
        )
        assert accepted.status_code == 201, "但作为工作区完全可用"


def test_default_browse_root_is_home(tmp_path: Path) -> None:
    settings = Settings(
        api_key="", base_url="http://127.0.0.1:1", model_name="m", workspace=tmp_path
    )
    assert settings.resolved_browse_root == Path.home().resolve()


def test_browse_root_can_be_overridden(tmp_path: Path) -> None:
    settings = Settings(
        api_key="",
        base_url="http://127.0.0.1:1",
        model_name="m",
        workspace=tmp_path,
        browse_root=tmp_path,
    )
    assert settings.resolved_browse_root == tmp_path.resolve()


async def test_browse_rejects_a_file(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    async with _client(_settings(tmp_path)) as client:
        response = await client.get("/api/fs/dirs", params={"path": "a.txt"})
    assert response.status_code == 400


# ---------------------------------------------------------------- 无模型模式


async def test_stub_model_runs_without_any_api_key(tmp_path: Path) -> None:
    """无模型模式的立身之本：没有任何密钥、零 token，也能跑完整条链路。"""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("NEEDLE = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")

    settings = _settings(tmp_path)  # api_key 为空
    async with _client(settings) as client:
        response = await client.post(
            "/api/tasks",
            json={"task": "在仓库里找 NEEDLE", "workspace": str(tmp_path), "model": STUB_MODEL_ID},
        )
        assert response.status_code == 201
        events = await _wait_finished(client, response.json()["task_id"])

    kinds = [event["type"] for event in events]
    assert "tool.started" in kinds, "无模型模式也要产生真实工具调用事件"
    assert "tool.finished" in kinds
    assert kinds[-1] == "task.finished"

    final = events[-1]["data"]
    assert final["status"] == "done"
    assert final["budget"]["tokens_in"] == 0, "零 token"
    assert final["budget"]["cost_cny"] == 0, "零成本"
    assert "无模型模式" in final["summary"]


async def test_stub_tool_events_carry_real_tool_names(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("VALUE = 1\n", encoding="utf-8")

    settings = _settings(tmp_path)
    async with _client(settings) as client:
        response = await client.post(
            "/api/tasks",
            json={"task": "看看 VALUE", "workspace": str(tmp_path), "model": STUB_MODEL_ID},
        )
        events = await _wait_finished(client, response.json()["task_id"])

    started = {event["data"]["name"] for event in events if event["type"] == "tool.started"}
    assert {"list_dir", "glob", "read"} <= started


async def test_stub_mode_still_loads_the_project_doc(tmp_path: Path) -> None:
    """无模型模式不应绕过链路 —— 方向性文档加载同样要生效。"""
    (tmp_path / "AGENTS.md").write_text("# 约定\n入口在 src/\n", encoding="utf-8")

    settings = _settings(tmp_path)
    async with _client(settings) as client:
        response = await client.post(
            "/api/tasks",
            json={"task": "读一下项目", "workspace": str(tmp_path), "model": STUB_MODEL_ID},
        )
        events = await _wait_finished(client, response.json()["task_id"])

    summary = _assistant_text(events)
    assert "已载入 `AGENTS.md`" in summary


async def test_stub_mode_says_so_when_no_project_doc(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    async with _client(settings) as client:
        response = await client.post(
            "/api/tasks",
            json={"task": "读一下项目", "workspace": str(tmp_path), "model": STUB_MODEL_ID},
        )
        events = await _wait_finished(client, response.json()["task_id"])

    assert "未提供" in _assistant_text(events)


# ---------------------------------------------------------------- 参数校验


async def test_unknown_model_is_rejected_not_silently_defaulted(tmp_path: Path) -> None:
    """静默回退到默认模型会让用户以为跑的是自己选的模型 —— 必须报错。"""
    async with _client(_settings(tmp_path)) as client:
        response = await client.post(
            "/api/tasks", json={"task": "x", "workspace": str(tmp_path), "model": "gpt-9"}
        )
    assert response.status_code == 400
    assert "未知模型" in response.json()["detail"]


async def test_missing_workspace_is_rejected(tmp_path: Path) -> None:
    async with _client(_settings(tmp_path)) as client:
        response = await client.post(
            "/api/tasks", json={"task": "x", "workspace": str(tmp_path / "nope")}
        )
    assert response.status_code == 400


# ---------------------------------------------------------------- 关键词启发式


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        ("读取 `slugify` 的用法", "slugify"),
        ("说明 engine.py 和 models.py 的关系", "engine"),
        ("Config 是怎么被用上的", "Config"),
        # 一整句中文不能当关键词 —— 当正则必然 0 命中，界面上看起来像功能坏了
        ("读取这个目录下的所有文件", None),
        # 退而取短中文词。启发式刻意做得简单（这是 stub，不是产品逻辑），
        # 取到不理想的词也不要紧：search 会如实回报 0 命中，不会编造结果。
        ("看看 src 里的东西", "里的东西"),
        ("", None),
    ],
)
def test_keyword_picks_something_usable(task: str, expected: str | None) -> None:
    assert _keyword(task) == expected


def test_keyword_never_produces_a_regex_bomb() -> None:
    """挑出来的词只含标识符字符与中文，直接当正则用不会炸。"""
    for task in ("用 `a(b[c` 搜一下", "找找 (.*)+ 这类模式", "看看 [abc] 在哪"):
        picked = _keyword(task)
        if picked is not None:
            import re as _re

            _re.compile(picked)  # 不抛异常即通过
