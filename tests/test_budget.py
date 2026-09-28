from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from hajime2code.budget import UsageTracker, budget_from_message
from hajime2code.config import Pricing

PRICING = Pricing(cache_hit_per_mtok=1.0, cache_miss_per_mtok=2.0, output_per_mtok=4.0)


def _result(message: AIMessage) -> LLMResult:
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def test_reads_cache_hit_from_usage_metadata_details() -> None:
    message = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": 1000,
            "output_tokens": 100,
            "total_tokens": 1100,
            "input_token_details": {"cache_read": 400},
        },
    )
    budget = budget_from_message(message, PRICING)
    assert budget["cache_hit_tokens"] == 400
    assert budget["cache_miss_tokens"] == 600
    assert budget["llm_calls"] == 1
    # 400*1 + 600*2 + 100*4 = 2000 单位 / 百万 = 0.002
    assert budget["cost_cny"] == pytest.approx(0.002)


def test_falls_back_to_deepseek_raw_token_usage() -> None:
    message = AIMessage(
        content="ok",
        response_metadata={
            "token_usage": {
                "prompt_tokens": 500,
                "completion_tokens": 50,
                "prompt_cache_hit_tokens": 200,
            }
        },
    )
    budget = budget_from_message(message, PRICING)
    assert budget["tokens_in"] == 500
    assert budget["tokens_out"] == 50
    assert budget["cache_hit_tokens"] == 200
    assert budget["cache_miss_tokens"] == 300


def test_cache_hit_is_clamped_to_input_tokens() -> None:
    message = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": 10,
            "output_tokens": 1,
            "total_tokens": 11,
            "input_token_details": {"cache_read": 999},
        },
    )
    budget = budget_from_message(message, PRICING)
    assert budget["cache_hit_tokens"] == 10
    assert budget["cache_miss_tokens"] == 0


def test_missing_usage_yields_zero_cost() -> None:
    budget = budget_from_message(AIMessage(content="ok"), PRICING)
    assert budget["tokens_in"] == 0
    assert budget["cost_cny"] == 0.0


def test_tracker_accumulates_across_calls() -> None:
    tracker = UsageTracker(PRICING)
    result = _result(
        AIMessage(
            content="a",
            usage_metadata={"input_tokens": 10, "output_tokens": 1, "total_tokens": 11},
        )
    )
    tracker.on_llm_end(result)
    tracker.on_llm_end(result)
    assert tracker.total["llm_calls"] == 2
    assert tracker.total["tokens_in"] == 20
    assert tracker.total["tokens_out"] == 2


def test_tracker_ignores_non_chat_generations() -> None:
    from langchain_core.outputs import Generation

    tracker = UsageTracker(PRICING)
    tracker.on_llm_end(LLMResult(generations=[[Generation(text="plain")]]))
    assert tracker.total["llm_calls"] == 0
