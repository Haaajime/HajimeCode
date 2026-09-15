"""Todo 计划系统单测 —— 全部离线,零 API 消耗。"""
from __future__ import annotations

from agent_harness.todos import TodoError, TodoList, TodoStatus, build_todo_system
from agent_harness.tools import ToolRegistry


def test_add_and_complete_flow():
    tl = TodoList()
    i0 = tl.add("第一步")
    i1 = tl.add("第二步")
    assert i0 == 0 and i1 == 1
    tl.started(0)
    tl.complete(0)
    assert tl._items[0]["status"] == TodoStatus.COMPLETED
    assert tl._items[1]["status"] == TodoStatus.PENDING


def test_revert_and_replace():
    tl = TodoList()
    tl.add("task")
    tl.complete(0)
    tl.revert(0)
    assert tl._items[0]["status"] == TodoStatus.PENDING
    tl.replace(0, "改写")
    assert tl._items[0]["content"] == "改写"


def test_abort_clears():
    tl = TodoList()
    tl.add("x")
    tl.abort()
    assert not tl._items


def test_index_out_of_range_raises():
    tl = TodoList()
    tl.add("x")
    try:
        tl.complete(5)
        raise AssertionError("should raise")
    except TodoError:
        pass


def test_to_text_formats_status():
    tl = TodoList()
    tl.add("a")
    tl.add("b")
    tl.complete(1)
    text = tl.to_text()
    assert "[ ] 0" in text and "[x] 1" in text


def test_update_todo_tool_roundtrip():
    tl, tool, _ = build_todo_system()
    reg = ToolRegistry()
    reg.register(tool)
    out = reg.dispatch("update_todo", {"action": "add", "content": "调研"})
    assert "已添加任务 0" in out
    out = reg.dispatch("update_todo", {"action": "complete", "index": 0})
    assert "[x] 0: 调研" in out
    out = reg.dispatch("update_todo", {"action": "complete", "index": 9})
    assert "tool_error" in out


def test_hook_injects_todo_message():
    tl, _, hook = build_todo_system()
    tl.add("任务A")
    messages = [{"role": "user", "content": "go"}]
    hook(messages)
    assert any("任务A" in m.get("content", "") for m in messages if m["role"] == "user")