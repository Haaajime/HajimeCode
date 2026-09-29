"""token / 成本 / 缓存命中统计。

DeepSeek 的上下文缓存按前缀自动命中。实测（2026-09-29，两次相同前缀的调用）
它在 usage 里同时给出两种形式：

- 扁平字段 prompt_cache_hit_tokens / prompt_cache_miss_tokens（DeepSeek 自己的扩展）
- 嵌套字段 prompt_tokens_details.cached_tokens（OpenAI 兼容写法）

而 LangChain 归一化的是**嵌套那个**，落进 usage_metadata.input_token_details.cache_read。
所以本模块优先读归一化字段，读不到再回退读原始的扁平字段——两条路实测取到的是同一个值
（命中时两者都是 512，当次输入 674 token），回退只是防御。

另一个值得记住的性质：**缓存只影响成本，不影响 token 数**。
命中与未命中的 input_tokens 完全相同，差别只在单价。这正是 E4「压缩 ↔ 缓存对抗」
实验的立足点——压缩省下的 token，可能同时毁掉前缀缓存，省的钱被吃回去。

成本单价可配置，是 E4 实验的数据来源。
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult

from .config import Pricing
from .graph.state import Budget, add_budget, empty_budget


def _cache_hit_tokens(usage: dict[str, Any], raw: dict[str, Any]) -> int:
    details: dict[str, Any] = usage.get("input_token_details") or {}
    hit = details.get("cache_read") or details.get("cache_hit") or 0
    if not hit:
        hit = raw.get("prompt_cache_hit_tokens") or 0
    return int(hit)


def budget_from_message(message: AIMessage, pricing: Pricing) -> Budget:
    """把一条 AIMessage 的用量换算成预算增量。"""
    usage: dict[str, Any] = dict(getattr(message, "usage_metadata", None) or {})
    raw_meta: dict[str, Any] = dict(getattr(message, "response_metadata", None) or {})
    raw: dict[str, Any] = dict(raw_meta.get("token_usage") or {})

    input_tokens = int(usage.get("input_tokens") or raw.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or raw.get("completion_tokens") or 0)
    cache_hit = min(_cache_hit_tokens(usage, raw), input_tokens)
    cache_miss = max(input_tokens - cache_hit, 0)

    return Budget(
        steps=0,
        llm_calls=1,
        tokens_in=input_tokens,
        tokens_out=output_tokens,
        cache_hit_tokens=cache_hit,
        cache_miss_tokens=cache_miss,
        cost_cny=pricing.cost_cny(
            cache_hit_tokens=cache_hit,
            cache_miss_tokens=cache_miss,
            output_tokens=output_tokens,
        ),
    )


def budgets_from_result(result: LLMResult, pricing: Pricing) -> Budget:
    total = empty_budget()
    for generation_list in result.generations:
        for generation in generation_list:
            message = getattr(generation, "message", None)
            if isinstance(message, AIMessage):
                total = add_budget(total, budget_from_message(message, pricing))
    return total


class UsageTracker(BaseCallbackHandler):
    """累计一次节点执行内所有 LLM 调用的用量。"""

    def __init__(self, pricing: Pricing) -> None:
        super().__init__()
        self.pricing = pricing
        self.total: Budget = empty_budget()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self.total = add_budget(self.total, budgets_from_result(response, self.pricing))
