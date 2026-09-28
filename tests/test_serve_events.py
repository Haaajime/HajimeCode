"""事件翻译层单测：用实测到的 LangGraph 流形状构造输入。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from hajime2code.serve.events import extract_state_patch, normalize, translate


def test_normalize_accepts_two_and_three_tuples() -> None:
    assert normalize(("updates", {"a": 1})) == ((), "updates", {"a": 1})
    assert normalize((("sub",), "updates", {"a": 1})) == (("sub",), "updates", {"a": 1})


def test_debug_task_becomes_node_started() -> None:
    item = (
        (),
        "debug",
        {"step": 3, "type": "task", "payload": {"name": "plan", "id": "x"}},
    )
    assert [t.type for t in translate(item)] == ["node.started"]
    assert translate(item)[0].data == {"node": "plan", "step": 3}


def test_debug_task_result_becomes_node_finished() -> None:
    item = (
        (),
        "debug",
        {"step": 3, "type": "task_result", "payload": {"name": "act", "error": None}},
    )
    assert translate(item)[0].data["node"] == "act"


def test_debug_checkpoint_is_ignored() -> None:
    assert translate(((), "debug", {"type": "checkpoint", "payload": {}})) == []


def test_updates_budget_becomes_delta_event() -> None:
    item = ((), "updates", {"act": {"budget": {"steps": 1, "tokens_in": 10}}})
    events = translate(item)
    assert [e.type for e in events] == ["budget.updated"]
    assert events[0].data["delta"]["steps"] == 1


def test_updates_extracts_tool_calls_and_results() -> None:
    item = (
        (),
        "updates",
        {
            "model": {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "read", "args": {"path": "a.py"}, "id": "c1"}],
                    ),
                    ToolMessage(content="文件内容", tool_call_id="c1", name="read"),
                ]
            }
        },
    )
    kinds = [e.type for e in translate(item)]
    assert kinds == ["tool.started", "tool.finished"]
    finished = translate(item)[1]
    assert finished.data["name"] == "read"
    assert finished.data["ok"] is True


def test_updates_marks_failed_tool() -> None:
    item = (
        (),
        "updates",
        {
            "model": {
                "messages": [
                    ToolMessage(
                        content="[tool_error] 越界", tool_call_id="c1", name="read", status="error"
                    )
                ]
            }
        },
    )
    assert translate(item)[0].data["ok"] is False


def test_updates_emits_assistant_text() -> None:
    item = ((), "updates", {"act": {"messages": [AIMessage(content="我完成了")]}})
    events = translate(item)
    assert [e.type for e in events] == ["assistant.message"]
    assert events[0].data["text"] == "我完成了"


def test_messages_mode_becomes_llm_token() -> None:
    chunk = AIMessageChunk(content="你好")
    item = ((), "messages", (chunk, {"langgraph_node": "act"}))
    events = translate(item)
    assert events[0].type == "llm.token"
    assert events[0].data == {"node": "act", "text": "你好"}


def test_messages_mode_skips_empty_chunks() -> None:
    item = ((), "messages", (AIMessageChunk(content=""), {"langgraph_node": "act"}))
    assert translate(item) == []


def test_messages_mode_ignores_non_model_messages() -> None:
    """messages 模式会把节点写入的普通消息也流出来，不能当成模型 token。"""
    item = ((), "messages", (HumanMessage(content="用户输入的任务"), {"langgraph_node": "intake"}))
    assert translate(item) == []


def test_extract_state_patch_merges_node_outputs() -> None:
    item = ((), "updates", {"reflect": {"status": "done", "summary": "完成"}})
    patch = extract_state_patch(item)
    assert patch is not None
    assert patch["status"] == "done"
    assert patch["summary"] == "完成"


def test_extract_state_patch_ignores_non_updates() -> None:
    assert extract_state_patch(((), "messages", (AIMessageChunk(content="x"), {}))) is None
