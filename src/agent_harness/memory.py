"""记忆系统:跨会话留存与召回,支持"选取-抽取-合并"。

- 选取(recall):按 标签/键/值 的子串命中打分召回最相关记忆。
- 抽取(remember):把一条事实写入记忆库(按 key 去重更新)。
- 合并(merge):批量写入;冲突 key 覆盖,并可用 summarizer 做内容合并(可选项)。
- 持久化:MemoryStore 可与磁盘文件绑定,构造时载入、更新后 save 落盘,实现跨会话留存。

provides:
- MemoryStore(核心)
- remember_tool(store): 供模型写入记忆的 update_memory 工具
- make_memory_start_hook(store): 在会话开头注入已有记忆(仅注入一次)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .hooks import PreTurnFn
from .tools import Tool

Summarizer = Callable[[str], str]

_MISSING = object()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Memory:
    key: str
    value: str
    tags: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=_now)


class MemoryStore:
    def __init__(self, path: Path | None = None, summarizer: Summarizer | None = None) -> None:
        self.path = path
        self.summarizer = summarizer
        self._mem: dict[str, Memory] = {}
        if path is not None and path.exists():
            self._load(path)

    def _load(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 —— 损坏文件视为空库
            return
        items = data if isinstance(data, list) else []
        for it in items:
            m = Memory(**it)
            self._mem[m.key] = m

    def remember(self, key: str, value: str, tags: list[str] | None = None,
                 overwrite: bool = True) -> Memory:
        if key in self._mem and not overwrite:
            return self._mem[key]
        mem = Memory(key=key, value=value, tags=tags or [], updated_at=_now())
        self._mem[key] = mem
        return mem

    def recall(self, query: str, top_k: int = 3) -> list[Memory]:
        q = query.lower()
        scored = []
        for m in self._mem.values():
            scope = " ".join([m.key, m.value] + m.tags).lower()
            score = scope.count(q) + (3 if q in m.key.lower() else 0)
            if score > 0:
                scored.append((score, m))
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored[:top_k]]

    def merge(self, facts: list[tuple[str, str]]) -> int:
        n = 0
        for key, value in facts:
            self.remember(key, value)
            n += 1
        return n

    def forget(self, key: str) -> None:
        self._mem.pop(key, None)

    def get(self, key: str, default: Any = _MISSING) -> Memory:
        if key in self._mem:
            return self._mem[key]
        if default is _MISSING:
            raise KeyError(key)
        return default

    def save(self) -> None:
        if self.path is None:
            return
        payload = [
            {"key": m.key, "value": m.value, "tags": m.tags,
             "updated_at": m.updated_at}
            for m in self._mem.values()
        ]
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")

    def to_text(self) -> str:
        if not self._mem:
            return "(暂无记忆)"
        lines = [f"- {m.key}: {m.value}" for m in self._mem.values()]
        return "\n".join(lines)

    def make_memory_start_hook(self, header: str = "已知背景记忆:") -> PreTurnFn:
        injected = {"done": False}

        def _hook(messages: list[dict[str, Any]]) -> None:
            if injected["done"] or not self._mem:
                return
            injected["done"] = True
            messages.append({"role": "user", "content": f"{header}\n{self.to_text()}"})

        return _hook


def remember_tool(store: MemoryStore) -> Tool:
    def _run(key: str, value: str, tags: str = "") -> str:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        store.remember(key, value, tag_list)
        store.save()
        return f"已记忆: {key} = {value}"

    return Tool(
        name="update_memory",
        description="把一条关键事实写入跨会话记忆(按 key 覆盖)。tags 用逗号分隔可选。",
        parameters={
            "key": {"type": "string", "description": "记忆键", "required": True},
            "value": {"type": "string", "description": "记忆内容", "required": True},
            "tags": {"type": "string", "description": "逗号分隔的标签"},
        },
        func=_run,
    )


def build_memory_system(path: Path | None = None,
                        summarizer: Summarizer | None = None
                        ) -> tuple[MemoryStore, Tool, PreTurnFn]:
    store = MemoryStore(path=path, summarizer=summarizer)
    return store, remember_tool(store), store.make_memory_start_hook()