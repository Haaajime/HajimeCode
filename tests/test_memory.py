"""记忆系统单测 —— 全部离线,零 API 消耗。"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent_harness.memory import MemoryStore, build_memory_system
from agent_harness.tools import ToolRegistry


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


def test_remember_and_get(store: MemoryStore):
    store.remember("infra", "用 uv 管理环境,Python 3.10", tags=["env"])
    assert store.get("infra").value == "用 uv 管理环境,Python 3.10"
    assert store.get("infra").tags == ["env"]


def test_remember_overwrite_by_default(store: MemoryStore):
    store.remember("k", "v1")
    store.remember("k", "v2")
    assert store.get("k").value == "v2"
    store.remember("k", "v3", overwrite=False)
    assert store.get("k").value == "v2"


def test_recall_ranks_by_relevance(store: MemoryStore):
    store.remember("python", "用 Python 写代码", tags=["lang"])
    store.remember("rust", "Rust 用于系统层", tags=["lang"])
    hits = store.recall("python")
    assert hits and hits[0].key == "python"


def test_merge_bulk(store: MemoryStore):
    n = store.merge([("a", "1"), ("b", "2")])
    assert n == 2
    assert store.get("a").value == "1" and store.get("b").value == "2"


def test_persistence_roundtrip(tmp_path: Path):
    p = tmp_path / "mem.json"
    s1 = MemoryStore(path=p)
    s1.remember("project", "HajimeCode")
    s1.save()
    s2 = MemoryStore(path=p)
    assert s2.get("project").value == "HajimeCode"


def test_corrupt_file_treated_as_empty(tmp_path: Path):
    p = tmp_path / "mem.json"
    p.write_text("not json{{", encoding="utf-8")
    s = MemoryStore(path=p)
    assert len(s.recall("anything")) == 0


def test_memory_start_hook_injects_once(store: MemoryStore):
    store.remember("k", "v")
    hook = store.make_memory_start_hook()
    msgs1 = [{"role": "user", "content": "go"}]
    hook(msgs1)
    msgs2 = [{"role": "user", "content": "again"}]
    hook(msgs2)
    assert any("k: v" in m.get("content", "") for m in msgs1)
    # 第二次不再注入
    assert not any("k: v" in m.get("content", "") for m in msgs2)


def test_remember_tool_writes_and_saves(tmp_path: Path):
    p = tmp_path / "mem.json"
    store, tool, _ = build_memory_system(path=p)
    reg = ToolRegistry()
    reg.register(tool)
    out = reg.dispatch("update_memory", {"key": "model", "value": "deepseek", "tags": "llm,external"})
    assert "已记忆" in out
    assert p.exists()
    reloaded = MemoryStore(path=p)
    assert reloaded.get("model").value == "deepseek"