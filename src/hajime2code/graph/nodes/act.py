"""act：调用 ReAct 子图，执行一轮完整的工具交互。"""

from __future__ import annotations

from typing import Any, Protocol

from langchain_core.messages import AnyMessage

from ...budget import UsageTracker
from ...config import Pricing, Settings
from ..state import AgentState, NodeFn, add_budget


class AgentLike(Protocol):
    """只依赖 invoke，便于测试注入假实现。"""

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
        # 子图交回的是「输入 + 本轮新增」，这里全量交回主图即可，不用自己切。
        # 原因：messages 字段挂的是 add_messages reducer，它给没有 id 的消息补一个 id
        # 再按 id 合并，所以输入那部分会被原样替换回去，不会变成重复消息。
        #
        # 曾写成只回传新增部分（按长度切片），实测多轮重试后与全量回传的消息条数
        # 完全一致——证明切片是多余的；而且那种写法隐含一个位置假设：
        # 一旦子图只返回新增消息，切片就会把真实消息全部切掉。
        outgoing: list[AnyMessage] = list(result.get("messages") or [])
        return {
            "messages": outgoing,
            "budget": add_budget(tracker.total, {"steps": 1}),
        }

    return act
