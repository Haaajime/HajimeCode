"""主图状态定义。

- messages 用官方 add_messages reducer（追加、按 id 去重）。
- budget 用 add_budget reducer（累加），因为节点只上报增量。
- 其余通道为 last-value-wins，节点返回部分字段即可（total=False）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

TodoStatus = Literal["pending", "in_progress", "done"]
TaskStatus = Literal["running", "done", "failed"]


class Budget(TypedDict):
    """一次任务累计的资源消耗。字段均为增量累加量。"""

    steps: int
    llm_calls: int
    tokens_in: int
    tokens_out: int
    cache_hit_tokens: int
    cache_miss_tokens: int
    cost_cny: float


def empty_budget() -> Budget:
    return Budget(
        steps=0,
        llm_calls=0,
        tokens_in=0,
        tokens_out=0,
        cache_hit_tokens=0,
        cache_miss_tokens=0,
        cost_cny=0.0,
    )


def add_budget(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> Budget:
    """把两个（可能不完整的）预算增量相加。"""
    lhs = left or {}
    rhs = right or {}
    return Budget(
        steps=int(lhs.get("steps", 0)) + int(rhs.get("steps", 0)),
        llm_calls=int(lhs.get("llm_calls", 0)) + int(rhs.get("llm_calls", 0)),
        tokens_in=int(lhs.get("tokens_in", 0)) + int(rhs.get("tokens_in", 0)),
        tokens_out=int(lhs.get("tokens_out", 0)) + int(rhs.get("tokens_out", 0)),
        cache_hit_tokens=int(lhs.get("cache_hit_tokens", 0)) + int(rhs.get("cache_hit_tokens", 0)),
        cache_miss_tokens=int(lhs.get("cache_miss_tokens", 0))
        + int(rhs.get("cache_miss_tokens", 0)),
        cost_cny=float(lhs.get("cost_cny", 0.0)) + float(rhs.get("cost_cny", 0.0)),
    )


class Todo(TypedDict):
    id: str
    content: str
    status: TodoStatus


class Evidence(TypedDict, total=False):
    file: str
    line: int
    note: str


class AgentState(TypedDict, total=False):
    task: str
    messages: Annotated[list[AnyMessage], add_messages]
    todos: list[Todo]
    plan: list[str]
    budget: Annotated[Budget, add_budget]
    findings: list[Evidence]
    attempts: int
    status: TaskStatus
    summary: str
    # 工作区方向性文档（AGENTS.md / CLAUDE.md / README.md）—— 由 intake 载入
    project_brief: str
    project_brief_source: str


NodeFn = Callable[[AgentState], dict[str, Any]]
RouteFn = Callable[[AgentState], str]
