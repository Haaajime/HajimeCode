"""act：调用 ReAct 子图，执行一轮完整的工具交互。"""

from __future__ import annotations

from typing import Any, Protocol

from langchain_core.messages import AnyMessage

from ...budget import UsageTracker
from ...config import Pricing, Settings
from ..state import AgentState, NodeFn, add_budget


class AgentLike(Protocol):
    """只依赖 ``invoke``，便于测试注入假实现。"""

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any: ...


def make_act_node(agent: AgentLike, settings: Settings, pricing: Pricing | None = None) -> NodeFn:
    price = pricing or settings.pricing

    def act(state: AgentState) -> dict[str, Any]:
        tracker = UsageTracker(price)
        incoming: list[AnyMessage] = list(state.get("messages") or [])
        result = agent.invoke(
            {"messages": incoming},
            config={
                "callbacks": [tracker],
                "recursion_limit": 8 + settings.max_steps * 2,
            },
        )
        outgoing: list[AnyMessage] = list(result.get("messages") or [])
        # 子图基于 add_messages，会把输入消息原样作为前缀回传；只把新增部分交回主图，
        # 否则父子图之间会重复累积消息、平白放大 token。
        produced = outgoing[len(incoming) :] if len(outgoing) > len(incoming) else []
        return {
            "messages": produced,
            "budget": add_budget(tracker.total, {"steps": 1}),
        }

    return act
