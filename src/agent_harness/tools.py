"""工具抽象与分发注册表。

- Tool: name/description/参数 JSON Schema + func(返回字符串)。
- ToolRegistry: 注册/列出 schema/分发;新工具注册即可用,不动 Agent 主循环。
- 工具执行异常会被捕获并作为 tool_result 返回,让模型自行纠错,不会中断整个循环。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypedDict


class ToolSchema(TypedDict):
    type: str
    function: dict[str, Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema 的 properties/required
    func: Callable[..., str]

    def schema(self) -> ToolSchema:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": [
                        k for k, v in self.parameters.items() if v.get("required")
                    ],
                },
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[ToolSchema]:
        return [t.schema() for t in self._tools.values()]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"[tool_error] 未知工具: {name}"
        try:
            result = tool.func(**arguments)
            return str(result)
        except Exception as exc:  # noqa: BLE001 —— 工具异常回传给模型,不中断循环
            return f"[tool_error] {name} 执行失败: {exc}"


def _add(a: int, b: int) -> str:
    return str(a + b)


def _echo(text: str) -> str:
    return text


def default_registry() -> ToolRegistry:
    """预置几个安全的内置工具,用于验证工具调用往返。"""
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="add",
            description="计算两个整数的和。",
            parameters={
                "a": {"type": "integer", "description": "第一个加数", "required": True},
                "b": {"type": "integer", "description": "第二个加数", "required": True},
            },
            func=_add,
        )
    )
    reg.register(
        Tool(
            name="echo",
            description="原样返回传入的文本,用于测试。",
            parameters={
                "text": {"type": "string", "description": "要回显的文本", "required": True}
            },
            func=_echo,
        )
    )
    return reg