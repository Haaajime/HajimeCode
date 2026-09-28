"""reflect：验收当前进展，决定「继续执行」还是「收尾」。

注意这里多花了一次 LLM 调用做验收 —— 它本身就是一个**可消融的机制**：
E1 实验会对比「有 reflect 节点」与「无 reflect 节点」在 E 档（需多次试错）任务上的成功率与成本。
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from ...budget import UsageTracker
from ...config import Pricing, Settings
from ...prompts import JUDGE_SYSTEM
from ..state import AgentState, NodeFn, empty_budget


class Judgment(BaseModel):
    """验收结论。"""

    done: bool = Field(description="任务是否已经真正完成")
    reason: str = Field(description="判断依据，一句话")
    summary: str = Field(default="", description="若已完成，给出面向用户的结论摘要")


def make_llm_judge(model: BaseChatModel) -> Runnable[Any, Any]:
    prompt = ChatPromptTemplate.from_messages([("system", JUDGE_SYSTEM), ("human", "{brief}")])
    return prompt | model.with_structured_output(Judgment)


def _text_of(message: AnyMessage) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else str(content)


def _tail_text(messages: list[AnyMessage], limit: int = 2000) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and getattr(message, "content", None):
            return _text_of(message)[-limit:]
    return "（无）"


def _brief(state: AgentState) -> str:
    todos = state.get("todos") or []
    pending = [todo["content"] for todo in todos if todo.get("status") != "done"]
    return (
        f"## 任务\n{state.get('task', '')}\n\n"
        f"## 未完成待办\n{pending or '（无）'}\n\n"
        f"## 最近进展\n{_tail_text(list(state.get('messages') or []))}"
    )


def make_reflect_node(
    judge: Runnable[Any, Any], settings: Settings, pricing: Pricing | None = None
) -> NodeFn:
    price = pricing or settings.pricing

    def reflect(state: AgentState) -> dict[str, Any]:
        attempts = int(state.get("attempts", 0)) + 1
        used = state.get("budget") or empty_budget()
        tracker = UsageTracker(price)

        if used["steps"] >= settings.max_steps:
            return {
                "attempts": attempts,
                "status": "failed",
                "summary": f"达到步数上限（{settings.max_steps}），提前停止。",
                "budget": tracker.total,
            }

        verdict: Judgment = judge.invoke({"brief": _brief(state)}, config={"callbacks": [tracker]})

        if verdict.done:
            return {
                "attempts": attempts,
                "status": "done",
                "summary": verdict.summary or verdict.reason,
                "budget": tracker.total,
            }

        if attempts >= settings.max_attempts:
            return {
                "attempts": attempts,
                "status": "failed",
                "summary": f"重试 {attempts} 轮仍未通过验收：{verdict.reason}",
                "budget": tracker.total,
            }

        # 把验收意见回灌给下一轮 act，让重试有方向，而不是原样重复
        return {
            "attempts": attempts,
            "status": "running",
            "summary": verdict.reason,
            "messages": [
                HumanMessage(content=f"上一轮未通过验收：{verdict.reason}\n请针对性继续推进。")
            ],
            "budget": tracker.total,
        }

    return reflect


def route_after_reflect(state: AgentState) -> str:
    """条件边：未完成则回到 act，否则进 finalize。"""
    return "finalize" if state.get("status") in ("done", "failed") else "act"
