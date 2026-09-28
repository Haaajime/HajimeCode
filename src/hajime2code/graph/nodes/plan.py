"""plan：把任务拆解为有序步骤与待办清单。

planner 以 ``Runnable`` 注入，测试可换成纯离线实现，整图因此在零 API 下可跑通。
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from ...budget import UsageTracker
from ...config import Pricing
from ...models import structured_output
from ...prompts import PLAN_SYSTEM
from ..state import AgentState, NodeFn, Todo


class PlanResult(BaseModel):
    """规划结果：有序步骤 + 与之一一对应的待办项。"""

    steps: list[str] = Field(description="完成任务的有序步骤，每条一句话，动词开头")
    todos: list[str] = Field(default_factory=list, description="可勾选的待办清单，与 steps 对应")


def make_llm_planner(model: BaseChatModel) -> Runnable[Any, Any]:
    prompt = ChatPromptTemplate.from_messages([("system", PLAN_SYSTEM), ("human", "{brief}{task}")])
    return prompt | structured_output(model, PlanResult)


def _project_context(state: AgentState) -> str:
    """把方向性文档渲染成规划提示的前缀；没有则返回空串（模板里就是"无前缀"）。"""
    brief = (state.get("project_brief") or "").strip()
    if not brief:
        return ""
    source = state.get("project_brief_source") or "项目说明"
    return f"## 项目说明（来自 {source}）\n\n{brief}\n\n"


def make_plan_node(planner: Runnable[Any, Any], pricing: Pricing) -> NodeFn:
    def plan(state: AgentState) -> dict[str, Any]:
        tracker = UsageTracker(pricing)
        result: PlanResult = planner.invoke(
            {"task": state.get("task", ""), "brief": _project_context(state)},
            config={"callbacks": [tracker]},
        )
        items = list(result.todos) or list(result.steps)
        todos: list[Todo] = [
            Todo(id=f"t{index + 1}", content=content, status="pending")
            for index, content in enumerate(items)
        ]
        return {"plan": list(result.steps), "todos": todos, "budget": tracker.total}

    return plan
