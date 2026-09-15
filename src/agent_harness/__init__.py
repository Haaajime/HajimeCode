"""Agent Harness 框架 —— 类 Claude Code 的通用 Agent 载体。"""

from .compactor import ContextManager
from .file_tools import build_file_tools
from .hooks import Hooks, HookAction, HookResult
from .loop import agent_loop
from .permissions import Decision, PermissionManager, PermissionRule
from .providers import OpenAICompatibleProvider, ToolCall
from .todos import TodoList, TodoStatus, build_todo_system
from .tools import Tool, ToolRegistry, default_registry

__all__ = [
    "agent_loop",
    "build_file_tools",
    "build_todo_system",
    "ContextManager",
    "Decision",
    "HookAction",
    "Hooks",
    "HookResult",
    "OpenAICompatibleProvider",
    "PermissionManager",
    "PermissionRule",
    "ToolCall",
    "TodoList",
    "TodoStatus",
    "Tool",
    "ToolRegistry",
    "default_registry",
]

__version__ = "0.1.0"