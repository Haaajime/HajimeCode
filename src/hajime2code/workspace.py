"""工作区路径边界。

所有文件工具都必须经过 Workspace.resolve：路径解析后仍须落在工作区内，
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


def is_ignored_name(name: str) -> bool:
    """单个目录名是否属于"构建产物 / 工具缓存"（按名字判断，不涉及路径层级）。"""
    return name in IGNORED_DIR_NAMES


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

    def is_ignored(self, path: Path) -> bool:
        """路径是否落在被忽略的目录内。

        ⚠️ 只比较工作区内的相对部分。早先的实现直接看 path.parts（绝对路径），
        于是工作区自身路径里只要出现 build / dist / node_modules 之类的名字
        （例如工作区在 ~/build/myproj），整个工作区都会被判为忽略 ——
        glob 返回 []、list_dir 返回 0 项，而文件明明存在、read 也读得到。
        这种"静默全瞎"最难排查，故在此修正并保留说明。
        """
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            return False  # 工作区之外：交给 resolve 报越界，此处不做忽略判定
        return any(is_ignored_name(part) for part in relative.parts)
