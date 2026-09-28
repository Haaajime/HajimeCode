"""文件系统工具：read / glob / search / list_dir / write / edit。

设计约束：
- **全部** 经 ``Workspace.resolve`` 做路径边界校验，越界直接拒绝。
- 工具内部捕获异常并返回 ``[tool_error] ...`` 文本，让模型自行纠错，而不是中断整张图。
- ``write`` / ``edit`` 有副作用，**W3 起**会被权限中间件（fail-closed + 人工审批）拦截；
  这里只负责"能安全执行"，不负责"是否允许执行"。
- 列举类工具（``glob`` / ``list_dir`` / ``search``）**一律显式报告截断**，不静默少给。
"""

from __future__ import annotations

import json
import re
from fnmatch import fnmatch
from typing import Any

from langchain_core.tools import BaseTool, tool

from ..workspace import Workspace, WorkspaceError

MAX_LIST = 200
MAX_READ_CHARS = 60_000
BINARY_SNIFF_BYTES = 4096

# ---- search ----
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_LINE_CHARS = 300
MAX_SEARCH_FILE_BYTES = 1_000_000


def _err(exc: Exception) -> str:
    return f"[tool_error] {exc}"


def _clip(text: str, limit: int = MAX_SEARCH_LINE_CHARS) -> str:
    """把单行压到可比长度：长行（如压缩过的 JS）会撑爆上下文。"""
    stripped = text.rstrip()
    return stripped if len(stripped) <= limit else stripped[:limit] + "…"


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
            raw = target.read_bytes()
            # 二进制文件按文本读会得到大片乱码，既污染上下文又看不出问题，故直接说明。
            if b"\x00" in raw[:BINARY_SNIFF_BYTES]:
                return f"(已跳过二进制文件 {ws.relative(target)}：共 {len(raw)} 字节，非文本内容)"
            lines = raw.decode("utf-8", errors="replace").splitlines(keepends=True)
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
        """列出工作区内某目录的下一层内容（**不递归**）；目录以 / 结尾。

        若条目数超过上限，表头会显式标注"仅显示前 N 项"，**不要据此断定目录只有这些内容** ——
        此时应改用 glob 或逐个进入子目录。

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
            shown = rows[:MAX_LIST]
            head = f"(目录 {ws.relative(target)} 共 {len(rows)} 项"
            if len(rows) > len(shown):
                head += f"｜**仅显示前 {len(shown)} 项**，另有 {len(rows) - len(shown)} 项未列出"
            head += ")"
            return head + "\n" + "\n".join(shown)
        except (WorkspaceError, OSError) as exc:
            return _err(exc)

    @tool
    def glob(pattern: str, max_results: int = MAX_LIST) -> str:
        """按 glob 通配符列出工作区内的路径（支持 ** 递归），返回 JSON **对象**。

        返回形如 ``{"pattern", "returned", "total_matched", "truncated", "paths", "hint"?}``。
        **务必检查 ``truncated``**：为 true 时 ``paths`` 只是匹配结果的一部分，
        绝不能据此断定文件总数；请提高 ``max_results``，或用更精确的 pattern 缩小范围。

        Args:
            pattern: 通配符，如 'src/**/*.py'。
            max_results: 返回条数上限，默认 200。
        """
        try:
            if max_results <= 0:
                return "[tool_error] max_results 必须为正整数"
            matched: list[str] = []
            for candidate in sorted(ws.root.glob(pattern)):
                if ws.is_ignored(candidate):
                    continue
                rel = ws.relative(candidate)
                matched.append(rel + "/" if candidate.is_dir() else rel)

            shown = matched[:max_results]
            truncated = len(matched) > len(shown)
            payload: dict[str, Any] = {
                "pattern": pattern,
                "returned": len(shown),
                "total_matched": len(matched),
                "truncated": truncated,
                "paths": shown,
            }
            if truncated:
                payload["hint"] = (
                    f"结果被截断：匹配共 {len(matched)} 条，"
                    f"仅返回前 {len(shown)} 条（按路径排序）。"
                    f"请提高 max_results，或改用更精确的 pattern，不要据此断定文件总数。"
                )
            return json.dumps(payload, ensure_ascii=False)
        except (WorkspaceError, OSError, ValueError) as exc:
            return _err(exc)

    @tool
    def search(
        pattern: str,
        path: str = ".",
        file_pattern: str | None = None,
        ignore_case: bool = False,
        context_lines: int = 0,
        max_results: int = MAX_SEARCH_RESULTS,
    ) -> str:
        """在工作区的文件**内容**里按正则搜索（grep）。返回 JSON **对象**。

        这是"先定位、再阅读"的主力工具：先用它找到命中位置，再用 `read` 读上下文，
        **不要靠猜文件名**。适合定位某个函数/类/字符串定义或引用出现在哪里。

        返回形如 ``{"pattern", "path", "returned", "total_matched", "truncated",
        "files_scanned", "files_with_matches", "files_skipped_binary",
        "files_skipped_large", "matches", "hint"?}``。
        **务必检查 ``truncated``**：为 true 时 ``matches`` 不完整，
        请收窄 ``pattern`` 或 ``file_pattern`` 后重搜。

        Args:
            pattern: 正则表达式（Python ``re`` 语法）。
            path: 搜索起点（文件或目录），默认工作区根目录。
            file_pattern: 只搜匹配该 glob 的文件，如 ``'*.py'`` 或 ``'src/**/*.py'``。
            ignore_case: 是否忽略大小写。
            context_lines: 每条命中额外显示的上下文行数，0 表示只显示命中行。
            max_results: 命中条数上限，默认 50。
        """
        try:
            if not pattern:
                return "[tool_error] pattern 不能为空"
            if max_results <= 0:
                return "[tool_error] max_results 必须为正整数"
            if context_lines < 0:
                return "[tool_error] context_lines 不能为负"
            try:
                regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
            except re.error as exc:
                return f"[tool_error] 正则表达式无效：{exc}"

            start = ws.resolve(path)
            if start.is_file():
                candidates: list[Any] = [start]
            elif start.is_dir():
                candidates = sorted(p for p in start.rglob("*") if p.is_file())
            else:
                return f"[tool_error] 路径不存在：{path}"

            matches: list[dict[str, Any]] = []
            total = 0
            scanned = 0
            with_matches = 0
            skipped_binary = 0
            skipped_large = 0

            for candidate in candidates:
                if ws.is_ignored(candidate):
                    continue
                relative = ws.relative(candidate)
                if file_pattern and not (
                    fnmatch(relative, file_pattern) or fnmatch(candidate.name, file_pattern)
                ):
                    continue
                try:
                    if candidate.stat().st_size > MAX_SEARCH_FILE_BYTES:
                        skipped_large += 1
                        continue
                    raw = candidate.read_bytes()
                except OSError:
                    continue
                if b"\x00" in raw[:BINARY_SNIFF_BYTES]:
                    skipped_binary += 1
                    continue

                scanned += 1
                lines = raw.decode("utf-8", errors="replace").splitlines()
                hit_in_file = False
                for index, line in enumerate(lines):
                    if not regex.search(line):
                        continue
                    total += 1
                    hit_in_file = True
                    if len(matches) >= max_results:
                        continue  # 继续数总数，只为如实报告
                    entry: dict[str, Any] = {
                        "file": relative,
                        "line": index + 1,
                        "text": _clip(line.strip()),
                    }
                    if context_lines > 0:
                        low = max(0, index - context_lines)
                        high = min(len(lines), index + context_lines + 1)
                        entry["context"] = [
                            f"{number + 1}: {_clip(lines[number])}" for number in range(low, high)
                        ]
                    matches.append(entry)
                if hit_in_file:
                    with_matches += 1

            truncated = total > len(matches)
            payload: dict[str, Any] = {
                "pattern": pattern,
                "path": path,
                "returned": len(matches),
                "total_matched": total,
                "truncated": truncated,
                "files_scanned": scanned,
                "files_with_matches": with_matches,
                "files_skipped_binary": skipped_binary,
                "files_skipped_large": skipped_large,
                "matches": matches,
            }
            if truncated:
                payload["hint"] = (
                    f"结果被截断：命中共 {total} 条，仅返回前 {len(matches)} 条。"
                    f"请提高 max_results，或用更精确的 pattern / file_pattern 缩小范围。"
                )
            elif total == 0 and (skipped_binary or skipped_large):
                payload["hint"] = (
                    f"无命中，但有 {skipped_binary} 个二进制文件与 "
                    f"{skipped_large} 个超大文件被跳过；"
                    f"结论只对已扫描的 {scanned} 个文本文件成立。"
                )
            return json.dumps(payload, ensure_ascii=False)
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

    return [read, list_dir, glob, search, write, edit]
