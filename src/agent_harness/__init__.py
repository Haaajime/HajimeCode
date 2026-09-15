"""Agent Harness 框架 —— 类 Claude Code 的通用 Agent 载体。"""

from .file_tools import build_file_tools
from .hooks import Hooks, HookAction, HookResult
from .loop import agent_loop
from .permissions import Decision, PermissionManager, PermissionRule
from .providers import OpenAICompatibleProvider, ToolCall
from .tools import Tool, ToolRegistry, default_registry

__all__ = [
    "agent_loop",
    "build_file_tools",
    "Decision",
    "HookAction",
    "Hooks",
    "HookResult",
    "PermissionManager",
    "PermissionRule",
    "OpenAICompatibleProvider",
    "ToolCall",
    "Tool",
    "ToolRegistry",
    "default_registry",
]

__version__ = "0.1.0"