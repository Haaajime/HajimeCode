"""主图端到端离线测试：用假 planner / judge / agent 跑通全部控制流分支。"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from hajime2code.config import Settings
from hajime2code.graph.builder import build_default_graph, build_graph
from hajime2code.graph.nodes.plan import PlanResult
from hajime2code.graph.nodes.reflect import Judgment


class FakeAgent:
    """离线替身：回显输入消息并追加一条 AIMessage（模拟 create_agent 的返回形状）。"""

    def __init__(self, texts: list[str] | None = None) -> None:
        self._texts = texts or ["已完成初步探查。"]
        self.calls = 0

    def invoke(self, payload: Any, config: Any = None, **kwargs: Any) -> Any:
        messages = list(payload["messages"])
        text = self._texts[min(self.calls, len(self._texts) - 1)]
        self.calls += 1
        return {"messages": [*messages, AIMessage(content=text)]}


def _planner() -> RunnableLambda[Any, Any]:
    return RunnableLambda(
        lambda _payload: PlanResult(
            steps=["探查结构", "读取目标文件"],
            todos=["探查结构", "读取目标文件"],
        )
    )


def _judge(*verdicts: bool) -> RunnableLambda[Any, Any]:
    counter = {"index": 0}

    def decide(_payload: Any) -> Judgment:
        index = min(counter["index"], len(verdicts) - 1)
        counter["index"] += 1
        done = verdicts[index]
        return Judgment(
            done=done,
            reason="已完成" if done else "未完成，仍需继续",
            summary="任务完成" if done else "",
        )

    return RunnableLambda(decide)


def _graph(settings: Settings, judge: Any, agent: Any | None = None) -> Any:
    return build_graph(
        settings=settings,
        planner=_planner(),
        judge=judge,
        agent=agent or FakeAgent(),
    )


def test_finishes_when_judge_accepts(settings: Settings) -> None:
    state = _graph(settings, _judge(True)).invoke({"task": "看看项目结构"})
    assert state["status"] == "done"
    assert state["budget"]["steps"] == 1
    assert state["attempts"] == 1
    assert state["plan"] == ["探查结构", "读取目标文件"]
    assert [todo["content"] for todo in state["todos"]] == ["探查结构", "读取目标文件"]
    assert state["summary"] == "任务完成"


def test_retries_act_then_finishes(settings: Settings) -> None:
    agent = FakeAgent(["第一次尝试", "第二次尝试"])
    state = _graph(settings, _judge(False, True), agent).invoke({"task": "修一个 bug"})

    assert state["status"] == "done"
    assert state["budget"]["steps"] == 2
    assert state["attempts"] == 2
    assert agent.calls == 2, "验收失败后必须重新执行 act"


def test_retry_injects_feedback_into_messages(settings: Settings) -> None:
    agent = FakeAgent(["尝试"])
    state = _graph(settings, _judge(False, True), agent).invoke({"task": "修一个 bug"})
    assert any("未通过验收" in str(message.content) for message in state["messages"])


def test_stops_at_max_steps(settings: Settings) -> None:
    tight = settings.model_copy(update={"max_steps": 1, "max_attempts": 5})
    state = _graph(tight, _judge(False)).invoke({"task": "永远做不完的任务"})

    assert state["status"] == "failed"
    assert state["budget"]["steps"] == 1
    assert "步数上限" in state["summary"]


def test_gives_up_after_max_attempts(settings: Settings) -> None:
    loose = settings.model_copy(update={"max_steps": 50, "max_attempts": 2})
    agent = FakeAgent(["a", "b", "c"])
    state = _graph(loose, _judge(False), agent).invoke({"task": "做不完"})

    assert state["status"] == "failed"
    assert agent.calls == 2
    assert "未通过验收" in state["summary"]


def test_does_not_duplicate_messages_between_graphs(settings: Settings) -> None:
    agent = FakeAgent(["结论：完成"])
    state = _graph(settings, _judge(True), agent).invoke({"task": "任务"})
    contents = [str(message.content) for message in state["messages"]]

    assert contents.count("任务") == 1, "子图回显的前缀不应被重复写回主图"
    assert contents.count("结论：完成") == 1


def test_default_graph_assembly_makes_no_network_call(settings: Settings) -> None:
    graph = build_default_graph(settings)
    assert graph is not None
