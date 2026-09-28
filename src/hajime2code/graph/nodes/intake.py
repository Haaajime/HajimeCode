"""intake：把用户任务载入状态，并初始化流程控制字段。

除任务本身外，这里还负责**载入工作区的方向性文档**（AGENTS.md / CLAUDE.md / README.md）：
让项目自己声明它的结构，模型开局就有方向感，而不是从零摸索。
加载器以参数注入，便于离线测试。

注意：没有方向性文档时，首条消息**原样就是任务文本**（不额外包标题），
避免给下游与测试引入无谓的格式变化。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage

from ...project_doc import ProjectDoc
from ..state import AgentState, NodeFn

ProjectDocLoader = Callable[[], ProjectDoc | None]


def make_intake_node(project_doc: ProjectDocLoader | None = None) -> NodeFn:
    def intake(state: AgentState) -> dict[str, Any]:
        task = state.get("task", "")
        doc = project_doc() if project_doc is not None else None

        content = task if doc is None else f"{doc.as_section()}\n\n## 任务\n\n{task}"
        return {
            "status": "running",
            "attempts": 0,
            "todos": [],
            "findings": [],
            "project_brief": doc.text if doc is not None else "",
            "project_brief_source": doc.path if doc is not None else "",
            "messages": [HumanMessage(content=content)],
        }

    return intake
