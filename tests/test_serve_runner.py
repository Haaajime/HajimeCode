"""runner 单测：累计逻辑 + 用真实 create_agent 跑通全链路（离线）。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from hajime2code.config import Settings
from hajime2code.graph.agents import build_react_agent
from hajime2code.graph.builder import build_graph
from hajime2code.graph.nodes.plan import PlanResult
from hajime2code.graph.nodes.reflect import Judgment
from hajime2code.serve.bus import EventBus
from hajime2code.serve.runner import run_task
from hajime2code.serve.store import TaskStore


class FakeGraph:
    """按给定条目顺序产出，并记录调用参数。"""

    def __init__(self, items: list[Any]) -> None:
        self.items = items
        self.captured: dict[str, Any] = {}

    def stream(self, input: Any, config: Any = None, **kwargs: Any) -> Iterator[Any]:
        self.captured = {"input": input, "config": config, "kwargs": kwargs}
        yield from self.items


class ExplodingGraph:
    def stream(self, input: Any, config: Any = None, **kwargs: Any) -> Iterator[Any]:
        raise RuntimeError("图炸了")
        yield  # pragma: no cover


def _run(graph: Any, settings: Settings) -> tuple[EventBus, TaskStore, str]:
    bus, store = EventBus(), TaskStore()
    record = store.create(task="任务", workspace=str(settings.workspace))
    run_task(
        task_id=record.id,
        task="任务",
        workspace=Path(settings.workspace),
        graph_factory=lambda _ws, _model: graph,
        bus=bus,
        store=store,
        settings=settings,
    )
    return bus, store, record.id


def test_publishes_lifecycle_and_accumulates_budget(settings: Settings) -> None:
    graph = FakeGraph(
        [
            ((), "debug", {"step": 1, "type": "task", "payload": {"name": "intake"}}),
            ((), "updates", {"plan": {"budget": {"llm_calls": 1, "tokens_in": 100}}}),
            ((), "updates", {"act": {"budget": {"llm_calls": 2, "tokens_in": 50, "steps": 1}}}),
            (
                (),
                "updates",
                {"finalize": {"status": "done", "summary": "全部完成", "plan": ["a"], "todos": []}},
            ),
        ]
    )
    bus, store, task_id = _run(graph, settings)
    events = bus.history(task_id)

    assert events[0].type == "task.created"
    assert "node.started" in {e.type for e in events}

    budget_events = [e for e in events if e.type == "budget.updated"]
    assert [e.data["total"]["llm_calls"] for e in budget_events] == [1, 3]
    assert budget_events[-1].data["total"]["tokens_in"] == 150
    assert budget_events[-1].data["total"]["steps"] == 1

    final = events[-1]
    assert final.type == "task.finished"
    assert final.data["status"] == "done"
    assert final.data["summary"] == "全部完成"
    assert final.data["budget"]["tokens_in"] == 150

    assert store.get(task_id).status == "done"  # type: ignore[union-attr]


def test_requests_all_stream_modes_with_subgraphs(settings: Settings) -> None:
    bus, _store, _task_id = _run(FakeGraph([]), settings)
    graph = FakeGraph([])
    _run(graph, settings)
    assert graph.captured["kwargs"]["stream_mode"] == ["updates", "messages", "debug"]
    assert graph.captured["kwargs"]["subgraphs"] is True
    assert graph.captured["input"] == {"task": "任务"}
    assert bus.history("missing") == []


def test_failure_becomes_error_event(settings: Settings) -> None:
    bus, store, task_id = _run(ExplodingGraph(), settings)
    events = bus.history(task_id)

    assert events[-1].type == "error"
    assert "图炸了" in events[-1].data["message"]
    assert store.get(task_id).status == "failed"  # type: ignore[union-attr]


def _infinite(text: str) -> Iterator[AIMessage]:
    while True:
        yield AIMessage(content=text)


def _real_graph_factory(settings: Settings) -> Any:
    model = GenericFakeChatModel(messages=_infinite("我用假模型完成了任务。"))

    def factory(_workspace: Path, _model: str | None = None) -> Any:
        agent = build_react_agent(model, [], system_prompt="s")
        return build_graph(
            settings=settings,
            planner=RunnableLambda(lambda _p: PlanResult(steps=["探查"], todos=["探查"])),
            judge=RunnableLambda(lambda _p: Judgment(done=True, reason="ok", summary="完成")),
            agent=agent,
        )

    return factory


def test_end_to_end_with_real_agent_and_fake_model(settings: Settings) -> None:
    """不碰网络：真实 create_agent + 官方假模型，验证真实 stream 形状能被正确翻译。"""
    bus, store = EventBus(), TaskStore()
    record = store.create(task="随便一个任务", workspace=str(settings.workspace))

    run_task(
        task_id=record.id,
        task="随便一个任务",
        workspace=Path(settings.workspace),
        graph_factory=_real_graph_factory(settings),
        bus=bus,
        store=store,
        settings=settings,
    )

    events = bus.history(record.id)
    kinds = {event.type for event in events}

    assert "llm.token" in kinds, "真实 create_agent 的 token 流应当被翻译成 llm.token"
    assert {"node.started", "node.finished"} <= kinds
    assert events[-1].type == "task.finished"
    assert events[-1].data["status"] == "done"
    assert store.get(record.id).summary == "完成"  # type: ignore[union-attr]
