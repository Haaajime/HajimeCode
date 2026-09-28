"""工作区方向性文档加载（``AGENTS.md`` / ``CLAUDE.md`` / ``README.md``）。

**为什么要有这个**：行业对"代码库结构怎么进上下文"的实际答案是**让项目自己声明结构**，
而不是让工具去猜。Claude Code 的做法就是开局先把项目自述文档载入上下文，再用
glob / grep 按需探索。我们的 ``intake`` 原先完全不载，模型每进一个仓库都要从零摸索。
详见 ``docs/调研_代码库结构如何进上下文.md``。

**大小刻意收紧**：官方对同类"每次都要读"的文件的经验是**超过 200 行会降低遵循度**
（越长占的上下文越多、模型越容易忽略）。故默认上限 200 行 / 8000 字符，
超出部分截断并在正文里显式标注，绝不静默丢内容。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .workspace import Workspace

# 优先级从高到低：AGENTS.md 是跨工具共识，CLAUDE.md 是 Claude Code 约定，README 兜底。
CANDIDATE_NAMES: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md", "README.md")

MAX_LINES = 200
MAX_CHARS = 8000


@dataclass(frozen=True)
class ProjectDoc:
    """载入结果。``truncated`` 为真时 ``text`` 只是原文前缀。"""

    path: str
    text: str
    total_lines: int
    truncated: bool

    def as_section(self) -> str:
        """渲染成可注入消息的一节，含来源与截断说明。"""
        note = ""
        if self.truncated:
            note = f"（原文共 {self.total_lines} 行，此处只载入前 {MAX_LINES} 行）"
        return f"## 项目说明（来自 {self.path}）{note}\n\n{self.text}"


def load_project_doc(workspace: Workspace) -> ProjectDoc | None:
    """按优先级取**第一个存在**的候选文件；都不存在则返回 None。"""
    for name in CANDIDATE_NAMES:
        target: Path = workspace.root / name
        if not target.is_file():
            continue
        try:
            raw = target.read_bytes()
        except OSError:
            continue
        # 只取前缀，避免一个超大 README 把上下文吃光
        text = raw[: MAX_CHARS * 4].decode("utf-8", errors="replace")
        lines = text.splitlines()
        total_lines = len(lines)

        if total_lines > MAX_LINES:
            lines = lines[:MAX_LINES]
            truncated = True
        else:
            truncated = False

        body = "\n".join(lines)
        if len(body) > MAX_CHARS:
            body = body[:MAX_CHARS]
            truncated = True

        return ProjectDoc(
            path=name,
            text=body,
            total_lines=total_lines,
            truncated=truncated,
        )
    return None


def make_project_doc_loader(workspace: Workspace) -> Callable[[], ProjectDoc | None]:
    """绑定工作区的加载器，便于注入到 intake 节点里做离线测试。"""

    def loader() -> ProjectDoc | None:
        return load_project_doc(workspace)

    return loader
