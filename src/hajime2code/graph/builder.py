"""主图装配。

    START → intake → plan → act → reflect ─┬─→ act        未通过验收，带着意见重试
                                            └─→ finalize → END

act 内部是官方 create_agent 装配的 ReAct 子图；主图管的是图级控制流
（规划、验收、回退、预算裁剪），两者职责正交。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ..config import Settings
from ..models import build_chat_model
from ..project_doc import make_project_doc_loader
from ..workspace import Workspace
from .agents import build_react_agent
from .nodes.act import make_act_node
from .nodes.finalize import make_finalize_node
from .nodes.intake import make_intake_node
from .nodes.plan import make_llm_planner, make_plan_node
from .nodes.reflect import make_llm_judge, make_reflect_node, route_after_reflect
from .state import AgentState, NodeFn

NODE_INTAKE = "intake"
NODE_PLAN = "plan"
NODE_ACT = "act"
NODE_REFLECT = "reflect"
NODE_FINALIZE = "finalize"

_Builder = StateGraph[AgentState, None, AgentState, AgentState]


def _add_node(builder: _Builder, name: str, node: NodeFn) -> None:
    """注册节点。

    本项目的节点由工厂函数返回（为了注入 planner / judge / agent 以便离线测试与消融）。
    mypy 无法从这种"工厂返回的 Callable"推断出 add_node 的 NodeInputT，会退化成
    Never 并报重载不匹配；直接传入 def 函数则正常。这属于 mypy 对泛型 Callable
    实参的推断限制，运行时不受影响，因此在此集中做一次类型忽略。
    """
    builder.add_node(name, node)  # type: ignore[call-overload]


def build_graph(
    *,
    settings: Settings,
    planner: Runnable[Any, Any],
    judge: Runnable[Any, Any],
    agent: Any,
    checkpointer: Any | None = None,
    project_doc: Any | None = None,
) -> CompiledStateGraph:
    """装配主图。planner / judge / agent / project_doc 均可注入，便于离线测试与消融实验。"""
    builder = StateGraph(AgentState)

    _add_node(builder, NODE_INTAKE, make_intake_node(project_doc))
    _add_node(builder, NODE_PLAN, make_plan_node(planner, settings.pricing))
    _add_node(builder, NODE_ACT, make_act_node(agent, settings))
    _add_node(builder, NODE_REFLECT, make_reflect_node(judge, settings))
    _add_node(builder, NODE_FINALIZE, make_finalize_node())

    builder.add_edge(START, NODE_INTAKE)
    builder.add_edge(NODE_INTAKE, NODE_PLAN)
    builder.add_edge(NODE_PLAN, NODE_ACT)
    builder.add_edge(NODE_ACT, NODE_REFLECT)
    builder.add_conditional_edges(
        NODE_REFLECT,
        route_after_reflect,
        {NODE_ACT: NODE_ACT, NODE_FINALIZE: NODE_FINALIZE},
    )
    builder.add_edge(NODE_FINALIZE, END)

    return builder.compile(checkpointer=checkpointer, name="hajime2code")


def build_default_graph(
    settings: Settings,
    *,
    tools: Sequence[BaseTool] = (),
    middleware: Sequence[Any] = (),
    model: BaseChatModel | None = None,
    checkpointer: Any | None = None,
    workspace: Workspace | None = None,
) -> CompiledStateGraph:
    """按默认依赖装配：DeepSeek 模型 + 官方 ReAct 子图 + 规划/验收节点。

    传入 workspace 时，intake 会载入该工作区的方向性文档
    （AGENTS.md / CLAUDE.md / README.md）。
    """
    chat = model or build_chat_model(settings)
    agent = build_react_agent(chat, list(tools), middleware=middleware)
    doc_loader = make_project_doc_loader(workspace) if workspace is not None else None
    return build_graph(
        settings=settings,
        planner=make_llm_planner(chat),
        judge=make_llm_judge(chat),
        agent=agent,
        checkpointer=checkpointer,
        project_doc=doc_loader,
    )
