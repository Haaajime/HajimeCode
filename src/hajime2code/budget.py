"""token / 成本 / 缓存命中统计。

DeepSeek 的上下文缓存按**前缀**自动命中，OpenAI 兼容响应里带
``prompt_cache_hit_tokens`` / ``prompt_cache_miss_tokens``。LangChain 会把它归一化进
``usage_metadata.input_token_details.cache_read``；该字段缺失时回退读
``response_metadata.token_usage``。

成本单价可配置，是 E4「压缩 ↔ 缓存对抗」实验的数据来源。
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
