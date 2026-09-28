"""方向性文档加载（``AGENTS.md`` / ``CLAUDE.md`` / ``README.md``）与 intake 注入。

这一层解决的是"代码库结构怎么进上下文"：**让项目自己声明结构**，而不是让工具去猜。
判据同样偏"诚实"——超长必须截断并标注，绝不能静默丢内容让模型以为看全了。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from hajime2code.config import Settings
from hajime2code.graph.builder import build_graph
from hajime2code.graph.nodes.intake import make_intake_node
from hajime2code.graph.nodes.plan import PlanResult
from hajime2code.graph.nodes.reflect import Judgment
from hajime2code.project_doc import (
    MAX_CHARS,
    MAX_LINES,
    ProjectDoc,
    load_project_doc,
)
from hajime2code.workspace import Workspace

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


# ---------------------------------------------------------------- 选择优先级


def test_prefers_agents_md(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n约定 A\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n约定 C\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# README\n", encoding="utf-8")

    doc = load_project_doc(Workspace(tmp_path))
    assert doc is not None
    assert doc.path == "AGENTS.md"
    assert "约定 A" in doc.text


def test_falls_back_to_claude_md(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n约定 C\n", encoding="utf-8")
    doc = load_project_doc(Workspace(tmp_path))
    assert doc is not None and doc.path == "CLAUDE.md"


def test_falls_back_to_readme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# README\n放最后兜底\n", encoding="utf-8")
    doc = load_project_doc(Workspace(tmp_path))
    assert doc is not None and doc.path == "README.md"


def test_fixture_repo_exposes_its_agents_doc() -> None:
    """样例仓库自带 AGENTS.md，且优先级高于 README。"""
    doc = load_project_doc(Workspace(FIXTURE))
    assert doc is not None
    assert doc.path == "AGENTS.md"
    assert "程序入口" in doc.text


def test_returns_none_when_absent(tmp_path: Path) -> None:
    assert load_project_doc(Workspace(tmp_path)) is None


def test_not_fooled_by_a_directory_with_the_same_name(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").mkdir()
    assert load_project_doc(Workspace(tmp_path)) is None


# ---------------------------------------------------------------- 截断诚实性


def test_truncates_long_doc_and_says_so(tmp_path: Path) -> None:
    total = MAX_LINES + 120
    (tmp_path / "AGENTS.md").write_text(
        "\n".join(f"第 {index} 行" for index in range(total)), encoding="utf-8"
    )

    doc = load_project_doc(Workspace(tmp_path))
    assert doc is not None
    assert doc.truncated is True
    assert doc.total_lines == total, "必须报告原文真实行数"
    assert len(doc.text.splitlines()) == MAX_LINES
    assert f"原文共 {total} 行" in doc.as_section()


def test_caps_single_enormous_line(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("x" * (MAX_CHARS + 5000), encoding="utf-8")
    doc = load_project_doc(Workspace(tmp_path))
    assert doc is not None
    assert doc.truncated is True
    assert len(doc.text) <= MAX_CHARS


def test_short_doc_is_not_marked_truncated(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# 短文档\n两行。\n", encoding="utf-8")
    doc = load_project_doc(Workspace(tmp_path))
    assert doc is not None
    assert doc.truncated is False
    assert doc.text == "# 短文档\n两行。"


def test_handles_undecodable_bytes_without_crashing(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_bytes(b"# \xff\xfe\x00 broken\n")
    doc = load_project_doc(Workspace(tmp_path))
    assert doc is not None  # 不崩即可，内容按 errors="replace" 处理


# ---------------------------------------------------------------- intake 注入


def test_intake_injects_doc_and_task(tmp_path: Path) -> None:
    doc = ProjectDoc(path="AGENTS.md", text="项目约定：模块在 src/", total_lines=1, truncated=False)
    node = make_intake_node(lambda: doc)

    out = node({"task": "修一个 bug"})
    content = out["messages"][0].content

    assert "## 项目说明" in content
    assert "AGENTS.md" in content
    assert "项目约定：模块在 src/" in content
    assert "## 任务" in content
    assert content.rstrip().endswith("修一个 bug")
    assert out["project_brief"] == "项目约定：模块在 src/"
    assert out["project_brief_source"] == "AGENTS.md"


def test_intake_without_doc_keeps_message_verbatim() -> None:
    """没有方向性文档时，首条消息必须**原样**是任务，不额外包标题。"""
    out = make_intake_node(lambda: None)({"task": "任务"})
    assert out["messages"][0].content == "任务"
    assert out["project_brief"] == ""
    assert out["project_brief_source"] == ""


def test_intake_default_loader_is_optional() -> None:
    out = make_intake_node()({"task": "任务"})
    assert out["messages"][0].content == "任务"


# ---------------------------------------------------------------- 端到端


class _EchoAgent:
    def invoke(self, payload: Any, config: Any = None, **kwargs: Any) -> Any:
        return {"messages": [*payload["messages"], AIMessage(content="完成")]}


def test_project_brief_reaches_the_planner(settings: Settings) -> None:
    """规划阶段也必须看到项目说明 —— 否则计划会脱离项目实际。"""
    seen: dict[str, Any] = {}

    def planner(payload: dict[str, Any]) -> PlanResult:
        seen.update(payload)
        return PlanResult(steps=["一步"], todos=["一步"])

    doc = ProjectDoc(path="AGENTS.md", text="约定：所有代码在 src/", total_lines=1, truncated=False)
    graph = build_graph(
        settings=settings,
        planner=RunnableLambda(planner),
        judge=RunnableLambda(lambda _p: Judgment(done=True, reason="ok", summary="done")),
        agent=_EchoAgent(),
        project_doc=lambda: doc,
    )
    state = graph.invoke({"task": "看看结构"})

    assert "约定：所有代码在 src/" in seen["brief"]
    assert seen["task"] == "看看结构"
    assert state["status"] == "done"
    assert state["project_brief"] == "约定：所有代码在 src/"
