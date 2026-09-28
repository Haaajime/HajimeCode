"""无模型模式：**真图 + 真工具 + 假决策**，零 API 成本。

为什么需要它：本项目的图、工具、事件协议、前端时间线都是真实产物，但"跑一次"
默认要花真实模型的钱。无模型模式让整条链路能**在没有密钥的情况下**跑通 ——
节点是真节点、工具是真工具、工作区是真工作区，只有"模型决策"是脚本化的。

与"注入一个假 chat model"的区别：假模型仍要走 ``create_agent`` 与
``structured_output``，而这里**连模型都不需要**，对 DeepSeek 的 function calling
没有任何依赖（因此它也不受 provider 兼容性问题影响）。

⚠️ 诚实说明：没有 token 级流式输出，预算恒为 0，结论是固定套路而非真推理。
**只适用于验证链路与手动体验，不能用于任何结论性判断。**
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.graph.state import CompiledStateGraph

from ..config import Settings
from ..graph.builder import build_graph
from ..graph.nodes.plan import PlanResult
from ..graph.nodes.reflect import Judgment
from ..project_doc import make_project_doc_loader
from ..tools import build_fs_tools
from ..workspace import Workspace

STUB_MODEL_ID = "stub"
STUB_MODEL_LABEL = "无模型模式（真工具 + 假决策，零成本）"

MAX_STUB_GLOB = 40
MAX_STUB_SEARCH = 10
MAX_STUB_READ_TRIES = 3
MAX_STUB_TOOL_CHARS = 1200

_STEPS = (
    "列出工作区根目录",
    "递归枚举全部文件",
    "读取一个代表性文件",
    "汇总观察结果并说明这是无模型模式",
)


def _brief(text: Any, limit: int = MAX_STUB_TOOL_CHARS) -> str:
    value = text if isinstance(text, str) else str(text)
    return value if len(value) <= limit else value[:limit] + "…(截断)"


class _StubAgent:
    """脚本化的"模型"：按固定套路调用**真实工具**，产出真实的工具调用/结果消息。

    形状刻意对齐 ``create_agent`` —— 返回 ``{"messages": [*输入, *新增]}``，
    这样 ``act`` 节点"只把新增部分交回主图"的裁剪逻辑无需任何特判。
    """

    def __init__(self, tools: dict[str, Any]) -> None:
        self._tools = tools
        self._counter = 0

    def _call(self, name: str, args: dict[str, Any]) -> tuple[AIMessage, ToolMessage]:
        call_id = f"stub-{self._counter}"
        self._counter += 1
        request = AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
        )
        try:
            raw = self._tools[name].invoke(args)
        except Exception as exc:  # 与真实路径一致：工具错误回传给"模型"，不中断整图
            raw = f"[tool_error] {type(exc).__name__}: {exc}"
        return request, ToolMessage(content=_brief(raw), name=name, tool_call_id=call_id)

    def _run(self, incoming: list[AnyMessage]) -> Iterator[AnyMessage]:
        # 取最近一条人类消息作为任务描述
        task = ""
        for message in reversed(incoming):
            if getattr(message, "type", "") == "human":
                task = str(message.content)
                break

        listing_request, listing = self._call("list_dir", {"path": "."})
        yield listing_request
        yield listing

        glob_request, globbed = self._call(
            "glob", {"pattern": "**/*", "max_results": MAX_STUB_GLOB}
        )
        yield glob_request
        yield globbed

        # 从任务里取一个关键词做真实内容检索 —— search 是"先定位再读"的主力工具
        keyword = _keyword(task)
        search_note = "（任务里没有可检索的关键词，跳过 search）"
        if keyword:
            search_request, found = self._call(
                "search", {"pattern": keyword, "max_results": MAX_STUB_SEARCH}
            )
            yield search_request
            yield found
            search_note = f"按关键词 `{keyword}` 检索到 {_total_of(found.content)} 处命中"

        paths = _paths_of(globbed.content)
        files = [path for path in paths if not path.endswith("/")]
        read_note = "（未找到可读的文本文件）"
        for candidate in files[:MAX_STUB_READ_TRIES]:
            request, result = self._call("read", {"path": candidate})
            yield request
            yield result
            if "已跳过二进制文件" not in str(result.content):
                read_note = f"读取了 `{candidate}`"
                break

        yield AIMessage(
            content=(
                f"【无模型模式】已完成一次链路演练，**没有使用任何大模型**。\n\n"
                f"- 任务：{_task_line(task)}\n"
                f"- 方向性文档：{_doc_note(task)}\n"
                f"- 步骤：list_dir → glob → search → read，全部是真实工具调用\n"
                f"- 工作区共观察到 {len(paths)} 个条目（glob 上限 {MAX_STUB_GLOB}）\n"
                f"- {search_note}\n"
                f"- {read_note}\n\n"
                "该模式用于零成本验证「图 → 工具 → 事件流 → 前端时间线」整条链路，"
                "结论是固定套路而非真实推理；需要真实结论请切换到具体模型。"
            )
        )

    def invoke(self, payload: Any, config: Any = None, **kwargs: Any) -> Any:
        incoming = list(payload["messages"])
        produced = list(self._run(incoming))
        return {"messages": [*incoming, *produced]}


def _paths_of(raw: Any) -> list[str]:
    """从 glob 的 JSON 对象里取回 paths；容忍非预期形状。"""
    try:
        payload = json.loads(str(raw))
    except (TypeError, ValueError):
        return []
    paths = payload.get("paths") if isinstance(payload, dict) else None
    return [str(item) for item in paths] if isinstance(paths, list) else []


def _total_of(raw: Any) -> int:
    """从 search 的 JSON 对象里取命中总数；容忍非预期形状。"""
    try:
        payload = json.loads(str(raw))
    except (TypeError, ValueError):
        return 0
    return int(payload.get("total_matched", 0)) if isinstance(payload, dict) else 0


_BACKTICKED = re.compile(r"`([^`\n]{2,64})`")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")

MAX_KEYWORD_CHARS = 48
MAX_CJK_KEYWORD_CHARS = 6


def _keyword(task: str) -> str | None:
    """挑一个可安全用作正则的检索关键词。

    优先级：任务里反引号显式标注的标识符 → 形似代码标识符的 ASCII 词 → 短中文词。

    刻意**避开一整句中文** —— 拿它当正则几乎必然 0 命中，界面上看起来就像功能坏了。
    只取标识符字符与中文，因此无需转义，不会因任务文本里的特殊字符炸掉正则。
    """
    for raw in _BACKTICKED.findall(task):
        candidate = raw.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
            return candidate

    identifiers = _IDENTIFIER.findall(task)
    if identifiers:
        return max(identifiers, key=len)[:MAX_KEYWORD_CHARS]

    short_cjk = [run for run in _CJK_RUN.findall(task) if len(run) <= MAX_CJK_KEYWORD_CHARS]
    return max(short_cjk, key=len) if short_cjk else None


def _task_line(raw: str) -> str:
    """首条人类消息里可能包含注入的「项目说明」，任务只是其中最后一节。"""
    marker = "## 任务\n\n"
    body = raw.split(marker, 1)[1] if marker in raw else raw
    stripped = body.strip()
    return stripped.splitlines()[0] if stripped else "（未提供）"


def _doc_note(raw: str) -> str:
    """报告方向性文档是否被载入 —— 无模型模式也不应绕过这一段链路。"""
    prefix = "## 项目说明（来自 "
    if prefix not in raw:
        return "本工作区未提供（AGENTS.md / CLAUDE.md / README.md 均不存在）"
    source = raw.split(prefix, 1)[1].split("）", 1)[0]
    return f"已载入 `{source}`"


def build_stub_graph(*, settings: Settings, workspace: Workspace) -> CompiledStateGraph:
    """装配无模型模式的主图（真实工具 + 脚本化决策）。"""
    tools = {tool.name: tool for tool in build_fs_tools(workspace)}
    planner: Runnable[Any, Any] = RunnableLambda(
        lambda _payload: PlanResult(steps=list(_STEPS), todos=list(_STEPS))
    )
    judge: Runnable[Any, Any] = RunnableLambda(
        lambda _payload: Judgment(
            done=True,
            reason="无模型模式：不做真实验收，直接收尾",
            summary="无模型模式演练完成（未使用大模型，结论不具参考性）。",
        )
    )
    return build_graph(
        settings=settings,
        planner=planner,
        judge=judge,
        agent=_StubAgent(tools),
        project_doc=make_project_doc_loader(workspace),
    )
