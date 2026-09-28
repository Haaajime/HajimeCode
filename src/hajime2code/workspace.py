"""工作区路径边界。

所有文件工具都必须经过 ``Workspace.resolve``：路径解析后仍须落在工作区内，
否则拒绝。这是 Agent 能安全获得读写能力的前提（也是权限层之外的第二道闸）。
"""

from __future__ import annotations

from pathlib import Path

IGNORED_DIR_NAMES = frozenset(
    {
        ".venv",
        ".git",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".idea",
        ".vscode",
        "dist",
        "build",
    }
)


class WorkspaceError(Exception):
    """工作区路径越界或参数非法；message 会作为 tool_result 回传给模型。"""


class Workspace:
    def __init__(self, root: str | Path) -> None:
        resolved = Path(root).expanduser().resolve()
        if not resolved.is_dir():
            raise WorkspaceError(f"工作区不是目录：{resolved}")
        self.root = resolved

    def resolve(self, raw: str) -> Path:
        """把用户/模型给出的路径解析为工作区内的绝对路径；越界即拒绝。"""
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise WorkspaceError(f"路径越界：{raw} 不在工作区 {self.root} 内")
        return path

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    @staticmethod
    def is_ignored(path: Path) -> bool:
        return any(part in IGNORED_DIR_NAMES for part in path.parts)
