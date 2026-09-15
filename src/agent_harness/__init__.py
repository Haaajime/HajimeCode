"""Agent Harness 框架 —— 类 Claude Code 的通用 Agent 载体。"""

from .loop import agent_loop
from .providers import OpenAICompatibleProvider, ToolCall
from .tools import Tool, ToolRegistry, default_registry

__all__ = [
    "agent_loop",
    "OpenAICompatibleProvider",
    "ToolCall",
    "Tool",
    "ToolRegistry",
    "default_registry",
]

__version__ = "0.1.0"