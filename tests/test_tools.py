"""工具抽象与注册表单测 —— 全部离线,零 API 消耗。"""
from __future__ import annotations

from agent_harness.tools import Tool, ToolRegistry


def _add(a: int, b: int) -> str:
    return str(a + b)


def test_schema_strips_property_level_required():
    """属性内部的 required 标记不应泄漏到发送给上游的 schema 中。"""
    t = Tool(
        name="add",
        description="求和",
        parameters={"a": {"type": "integer", "required": True}},
        func=_add,
    )
    params = t.schema()["function"]["parameters"]
    assert "required" not in params["properties"]["a"]
    assert params["required"] == ["a"]


def test_dispatch_unknown_tool_returns_error():
    reg = ToolRegistry()
    assert "未知工具" in reg.dispatch("nope", {})


def test_dispatch_exception_is_trapped():
    reg = ToolRegistry()
    reg.register(Tool(name="boom", description="", parameters={}, func=lambda: 1 / 0))
    assert "tool_error" in reg.dispatch("boom", {})


def test_dispatch_calls_func_with_kwargs():
    reg = ToolRegistry()
    reg.register(Tool(name="add", description="求和", parameters={}, func=_add))
    assert reg.dispatch("add", {"a": 2, "b": 3}) == "5"