from __future__ import annotations

import asyncio

from hajime2code.serve.bus import EventBus


async def test_late_subscriber_replays_history_then_closes() -> None:
    bus = EventBus()
    bus.publish("t1", "node.started", {"node": "intake"})
    bus.publish("t1", "task.finished", {"status": "done"})

    seen = [event.type async for event in bus.stream("t1")]
    assert seen == ["node.started", "task.finished"]


async def test_subscriber_receives_live_events() -> None:
    bus = EventBus()
    bus.bind_loop(asyncio.get_running_loop())

    received: list[str] = []

    async def consume() -> None:
        async for event in bus.stream("t2"):
            received.append(event.type)

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.02)  # 让订阅者先完成注册

    bus.publish("t2", "node.started", {})
    bus.publish("t2", "task.finished", {})

    await asyncio.wait_for(consumer, timeout=3)
    assert received == ["node.started", "task.finished"]


async def test_stream_respects_since_cursor() -> None:
    bus = EventBus()
    bus.publish("t3", "node.started", {})
    second = bus.publish("t3", "task.finished", {})

    seen = [event.seq async for event in bus.stream("t3", since=first_seq(second))]
    assert seen == [second.seq]


def first_seq(event: object) -> int:
    return getattr(event, "seq", 1) - 1


async def test_sequence_is_monotonic_per_task() -> None:
    bus = EventBus()
    a = bus.publish("t4", "node.started", {})
    b = bus.publish("t4", "node.finished", {})
    assert (a.seq, b.seq) == (1, 2)
    assert bus.publish("other", "node.started", {}).seq == 1


async def test_is_finished_detects_terminal_event() -> None:
    bus = EventBus()
    bus.publish("t5", "node.started", {})
    assert bus.is_finished("t5") is False
    bus.publish("t5", "error", {"message": "boom"})
    assert bus.is_finished("t5") is True
