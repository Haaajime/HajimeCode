"""只读文件系统工具(glob/read):为 coding 场景提供安全、只读的工作区访问。

安全边界:
- 所有访问被限定在 base_dir 工作区内:路径 resolve 后必须仍落在 base 内,防止穿越。
- 只读:glob 仅列路径,read 仅读文本,不做任何写/删操作。
- 结果一律以字符串返回(JSON),统一交由 ToolRegistry 回传。
"""
from __future__ import annotations

import json
from pathlib import Path

from .tools import Tool

_MAX_LIST = 200  # glob 返回条数上限,防止一条 tool_result 撑爆上下文
_MAX_READ_CHARS = 60_000  # read 的字符软上限,超限截断并注明


class WorkspaceError(Exception):
    """工作区路径越界或参数非法;message 会直接作为 tool_result 回传。"""


def _resolve_within(base: Path, raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = base / p
    p = p.resolve()
    if not p.is_relative_to(base):
        raise WorkspaceError(f"路径越界: {raw} 不在工作区 {base} 内")
    return p


def _relative_to_base(base: Path, p: Path) -> str:
    return p.relative_to(base).as_posix()


def _glob_func(base: Path):
    def _glob(pattern: str, sort: bool = True, recursive: bool = False) -> str:
        matches = [
            p
            for p in base.glob(pattern if not recursive else "**/" + pattern)
            if p.is_file()
        ]
        matches = sorted(matches) if sort else matches
        rel = [_relative_to_base(base, p) for p in matches[: _MAX_LIST]]
        return json.dumps(rel, ensure_ascii=False)

    return _glob


def _read_func(base: Path):
    def _read(path: str, offset: int = 0, limit: int | None = None) -> str:
        p = _resolve_within(base, path)
        if not p.is_file():
            raise WorkspaceError(f"不是可读文件: {path}")
        if offset < 0:
            raise WorkspaceError(f"offset 不能为负: {offset}")
        with p.open(encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        selected = lines[offset:] if limit is None else lines[offset : offset + limit]
        end = min(len(lines), offset + (limit if limit is not None else len(lines)))
        head = f"(文件 {_relative_to_base(base, p)} 共 {len(lines)} 行, 读取 {offset}..{end}) "
        raw = "".join(selected)
        output = raw[:_MAX_READ_CHARS]
        if len(raw) > _MAX_READ_CHARS:
            output += f"\n...[已截断,超 {_MAX_READ_CHARS} 字符]"
        return head + output

    return _read


def build_file_tools(base_dir: Path) -> list[Tool]:
    base = base_dir.resolve()
    return [
        Tool(
            name="glob",
            description="在项目工作区内按通配符列出文件路径(只读)。pattern 为相对工作区的路径,如 'src/**/*.py'。",
            parameters={
                "pattern": {"type": "string", "description": "glob 通配符,相对工作区", "required": True},
                "sort": {"type": "boolean", "description": "是否排序输出,默认 true"},
                "recursive": {"type": "boolean", "description": "是否为 ** 递归模式,默认 false"},
            },
            func=_glob_func(base),
        ),
        Tool(
            name="read",
            description="读取工作区内某个文本文件的部分或全部内容(只读)。path 相对工作区或绝对路径;可用 offset/limit 按行截取。",
            parameters={
                "path": {"type": "string", "description": "要读取的文件,相对或绝对", "required": True},
                "offset": {"type": "integer", "description": "从第几行开始(0-based),默认 0"},
                "limit": {"type": "integer", "description": "最多读取多少行,默认全部"},
            },
            func=_read_func(base),
        ),
    ]