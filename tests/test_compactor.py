"""上下文四级压缩单测 —— 全部离线,零 API 消耗。"""
from __future__ import annotations

from agent_harness.compactor import (
    ContextManager,
    _CHUNK,
    trim_message,
)


def _fake_summarize(text: str) -> str:
    return "摘要:" + text[-20:]


def test_l1_trims_largest_single_message():
    msgs = [
        {"role": "tool", "tool_call_id": "t", "content": "x" * 20_000},
    ]
    trim_message(msgs, 0)
    assert len(msgs[0]["content"]) <= _CHUNK
    assert "已按 L1 截断" in msgs[0]["content"]


def test_within_budget_does_nothing():
    cm = ContextManager(max_chars=1000, summarizer=_fake_summarize)
    msgs = [{"role": "user", "content": "hi"}]
    assert cm.compact(msgs) == 0
    assert msgs == [{"role": "user", "content": "hi"}]


def test_l2_summarize_oldest_tool_message():
    cm = ContextManager(max_chars=50, summarizer=_fake_summarize)
    msgs = [
        {"role": "tool", "tool_call_id": "t", "content": "A" * 100},
        {"role": "user", "content": "继续"},
    ]
    cm.compact(msgs)
    assert "摘要" in msgs[0]["content"]
    assert len(msgs[0]["content"]) < 100


def test_l4_archive_when_summarizer_missing():
    archived = []
    cm = ContextManager(max_chars=50, archive=lambda block: archived.append(block))
    msgs = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "b" * 80},
        {"role": "tool", "tool_call_id": "t", "content": "c" * 80},
    ]
    cm.compact(msgs)
    assert archived
    assert any("已归档" in m.get("content", "") for m in msgs)


def test_hook_if_over_budget_compacts():
    cm = ContextManager(max_chars=30, summarizer=_fake_summarize)
    hook = cm.to_hook()
    msgs = [{"role": "tool", "tool_call_id": "t", "content": "z" * 500}]
    hook(msgs)
    # 总字符应显著下降
    total = sum(len(str(m.get("content", ""))) for m in msgs)
    assert total < 200


def test_compact_reduces_and_terminates():
    # 归档指针消息本身不可再压,故只要求显著减少且不无限循环
    cm = ContextManager(max_chars=10, archive=lambda b: None)
    msgs = [{"role": "tool", "tool_call_id": "t", "content": "x" * 1000}]
    cm.compact(msgs)
    total = sum(len(str(m.get("content", ""))) for m in msgs)
    assert total < 100
    assert cm.total_evicted == 1