"""主图的状态定义。

状态是 LangGraph 里的一份共享数据，在整张图上流动：每个节点读它拿输入，
返回一个字典表示"本次要改哪些字段"，合并回去得到新状态。

先说清一个反复用到的概念。多个节点都会往同一个字段里写东西，默认规则是
后写的覆盖先写的。如果某个字段需要的是"合并"而不是"覆盖"，就得给它指定一个
合并函数（LangGraph 管它叫 reducer），由 LangGraph 把新旧值一起交给它，
拿它的返回值当结果。

messages：整条对话记录，可以理解为这次任务的短期记忆。
  父图、ReAct 子图、reflect 三方都会往里加消息，所以不能覆盖，必须合并。
  这里用的 add_messages 来自 LangGraph，它会给没有 id 的消息补一个 id，
  然后按 id 合并。这个性质很重要：同一批消息被重复交回时不会变成两份，
  而内容碰巧相同、但确实是两条的消息也不会被误合并。

budget：这次任务累计消耗了多少资源（步数、模型调用次数、输入输出 token、
  缓存命中 token、金额）。注意各节点只上报自己的增量——比如 act 上报
  "我用掉 1 步"——谁都不去读当前总数再算，所以它需要的是相加而非覆盖，
  用的就是下面这个 add_budget。

其余字段（status、summary、attempts、plan、todos 等）只有单个节点会写，
覆盖就够了，因此不指定合并函数，走默认行为。整个 TypedDict 声明为
total=False，是为了让节点只返回自己改动的字段，不必把整个状态填一遍。

文件末尾的 NodeFn 与 RouteFn 是两个类型别名，分别描述节点函数与条件边函数的形状。
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
