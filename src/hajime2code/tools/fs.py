"""文件系统工具：read / glob / list_dir / write / edit。

设计约束：
- **全部** 经 ``Workspace.resolve`` 做路径边界校验，越界直接拒绝。
- 工具内部捕获异常并返回 ``[tool_error] ...`` 文本，让模型自行纠错，而不是中断整张图。
- ``write`` / ``edit`` 有副作用，W4 起会被权限中间件（fail-closed + 人工审批）拦截；
  这里只负责"能安全执行"，不负责"是否允许执行"。
"""

from __future__ import annotations

import json

from langchain_core.tools import BaseTool, tool

from ..workspace import Workspace, WorkspaceError

MAX_LIST = 200
MAX_READ_CHARS = 60_000


def _err(exc: Exception) -> str:
    return f"[tool_error] {exc}"


def build_fs_tools(workspace: Workspace) -> list[BaseTool]:
    ws = workspace

    @tool
    def read(path: str, offset: int = 0, limit: int | None = None) -> str:
        """读取工作区内文本文件，可用 offset/limit 按行截取。

        Args:
            path: 相对工作区或工作区内的绝对路径。
            offset: 起始行号（0-based），默认 0。
            limit: 最多读取的行数，默认读到末尾。
        """
        try:
            target = ws.resolve(path)
            if not target.is_file():
                return f"[tool_error] 不是可读文件：{path}"
            if offset < 0:
                return "[tool_error] offset 不能为负"
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            end = len(lines) if limit is None else min(len(lines), offset + limit)
            chunk = "".join(lines[offset:end])
            truncated = len(chunk) > MAX_READ_CHARS
            if truncated:
                chunk = chunk[:MAX_READ_CHARS]
            head = f"(文件 {ws.relative(target)} 共 {len(lines)} 行，读取 {offset}..{end})\n"
            return head + chunk + ("\n...[已截断]" if truncated else "")
        except (WorkspaceError, OSError) as exc:
            return _err(exc)

    @tool
    def list_dir(path: str = ".") -> str:
        """列出工作区内某目录的下一层内容（不递归）；目录以 / 结尾。

        Args:
            path: 目录路径，默认工作区根目录。
        """
        try:
            target = ws.resolve(path)
            if not target.is_dir():
                return f"[tool_error] 不是目录：{path}"
            entries = sorted(
                (e for e in target.iterdir() if not ws.is_ignored(e)),
                key=lambda e: e.name,
            )
            rows = [e.name + "/" if e.is_dir() else e.name for e in entries]
            head = f"(目录 {ws.relative(target)} 共 {len(rows)} 项)"
            return head + "\n" + "\n".join(rows[:MAX_LIST])
        except (WorkspaceError, OSError) as exc:
            return _err(exc)

    @tool
    def glob(pattern: str, max_results: int = MAX_LIST) -> str:
        """按 glob 通配符列出工作区内的路径（支持 ** 递归），返回 JSON 数组。

        Args:
            pattern: 通配符，如 'src/**/*.py'。
            max_results: 返回条数上限。
        """
        try:
            matches: list[str] = []
            for candidate in sorted(ws.root.glob(pattern)):
                if ws.is_ignored(candidate):
                    continue
                rel = ws.relative(candidate)
                matches.append(rel + "/" if candidate.is_dir() else rel)
                if len(matches) >= max_results:
                    break
            return json.dumps(matches, ensure_ascii=False)
        except (WorkspaceError, OSError, ValueError) as exc:
            return _err(exc)

    @tool
    def write(path: str, content: str) -> str:
        """在工作区内创建或覆盖一个文本文件（父目录会自动创建）。有副作用。

        Args:
            path: 目标文件路径。
            content: 要写入的完整文本内容。
        """
        try:
            target = ws.resolve(path)
            if target.is_dir():
                return f"[tool_error] 目标是目录：{path}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"已写入 {ws.relative(target)}（{len(content)} 字符）"
        except (WorkspaceError, OSError) as exc:
            return _err(exc)

    @tool
    def edit(path: str, old_string: str, new_string: str = "", replace_all: bool = False) -> str:
        """对文件做精确字符串替换。有副作用。

        old_string 必须在文件中唯一出现，否则会拒绝执行（避免改错位置）。

        Args:
            path: 目标文件路径。
            old_string: 要被替换的原文片段。
            new_string: 替换后的新内容，默认为空（即删除该片段）。
            replace_all: 为 True 时替换全部出现，默认 False 只替换唯一命中处。
        """
        try:
            target = ws.resolve(path)
            if not target.is_file():
                return f"[tool_error] 文件不存在：{path}"
            text = target.read_text(encoding="utf-8")
            occurrences = text.count(old_string)
            if occurrences == 0:
                return "[tool_error] old_string 在文件中未找到，请先 read 确认原文"
            if occurrences > 1 and not replace_all:
                return (
                    f"[tool_error] old_string 出现 {occurrences} 次，不唯一；"
                    "请提供更长的上下文片段，或设置 replace_all=True"
                )
            updated = (
                text.replace(old_string, new_string)
                if replace_all
                else text.replace(old_string, new_string, 1)
            )
            target.write_text(updated, encoding="utf-8")
            replaced = occurrences if replace_all else 1
            return f"已编辑 {ws.relative(target)}：替换 {replaced} 处"
        except (WorkspaceError, OSError) as exc:
            return _err(exc)

    return [read, list_dir, glob, write, edit]
