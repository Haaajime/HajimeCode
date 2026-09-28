"""文件读取覆盖度：确保 Agent 能看到工作区里的**全部**内容。

这组测试针对两个曾经真实存在的"静默失败"（发现于 2026-09-28，见 docs/known_issues.md）：

1. ``Workspace.is_ignored`` 早先比较的是**绝对路径**的 parts，于是工作区自身路径里
   只要出现 ``build`` / ``dist`` / ``node_modules`` 之类的名字，整个工作区都被判为忽略 ——
   ``glob`` 返回 ``[]``、``list_dir`` 返回 0 项，而文件明明存在。Agent 会完全瞎掉。
2. ``glob`` / ``list_dir`` 的条数上限是**静默截断**：模型拿到的结果不全却无从得知，
   会据此给出错误的"文件总数"结论。

判据一律是"与磁盘真相逐条比对"，而不是"返回非空"。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from hajime2code.tools.fs import MAX_LIST, build_fs_tools
from hajime2code.workspace import IGNORED_DIR_NAMES, Workspace

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _tools(workspace: Workspace) -> dict[str, Any]:
    return {tool.name: tool for tool in build_fs_tools(workspace)}


def _glob(tools: dict[str, Any], pattern: str = "**/*", **kwargs: Any) -> dict[str, Any]:
    return json.loads(tools["glob"].invoke({"pattern": pattern, **kwargs}))


def _truth(root: Path) -> set[str]:
    """磁盘真相：排除被忽略目录后的全部条目（目录带尾 /，符号链接按文件算）。"""
    out: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIR_NAMES]
        if rel_dir != Path("."):
            out.add(rel_dir.as_posix() + "/")
        out.update((rel_dir / name).as_posix() for name in filenames)
    return out


@pytest.fixture
def repo() -> Workspace:
    return Workspace(FIXTURE)


# ---------------------------------------------------------------- 覆盖度


def test_glob_lists_every_entry_in_fixture(repo: Workspace) -> None:
    """glob 必须与磁盘真相逐条一致 —— 不漏、不多、不被截断。"""
    payload = _glob(_tools(repo))
    got = {path.rstrip("/") for path in payload["paths"]}
    truth = {path.rstrip("/") for path in _truth(FIXTURE)}

    assert payload["truncated"] is False
    assert payload["total_matched"] == len(truth)
    assert got == truth, f"漏掉={sorted(truth - got)} 多出={sorted(got - truth)}"


@pytest.mark.parametrize(
    "relative",
    [
        "README.md",
        "src/core/models.py",
        "docs/deep/nested/more/level3.md",
        "src/中文模块/常量.py",
        "中文目录/说明.md",
        "dir with spaces/note file.txt",
        "tests/fixtures/data.json",
        "empty_dir/.gitkeep",
    ],
)
def test_every_layer_is_reachable(repo: Workspace, relative: str) -> None:
    """深层嵌套 / 非 ASCII / 含空格 / 空文件都必须可读。"""
    tools = _tools(repo)
    listing = _glob(tools)
    assert relative in {path.rstrip("/") for path in listing["paths"]}
    assert not tools["read"].invoke({"path": relative}).startswith("[tool_error]")


def test_hidden_files_are_visible(repo: Workspace) -> None:
    paths = {path.rstrip("/") for path in _glob(_tools(repo))["paths"]}
    assert {".gitignore", ".env.example", "empty_dir/.gitkeep"} <= paths


def test_ignored_dirs_are_excluded_but_siblings_survive(tmp_path: Path) -> None:
    """被忽略目录要排除；同级的正常目录不能受牵连。"""
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "a.py").write_text("A = 1\n", encoding="utf-8")
    for ignored in ("node_modules", "__pycache__"):
        (tmp_path / ignored).mkdir()
        (tmp_path / ignored / "junk.bin").write_bytes(b"\x00junk")

    paths = {path.rstrip("/") for path in _glob(_tools(Workspace(tmp_path)))["paths"]}
    assert "keep/a.py" in paths
    assert not any(path.startswith(("node_modules", "__pycache__")) for path in paths)


def test_internal_symlink_readable_and_escaping_symlink_rejected(repo: Workspace) -> None:
    tools = _tools(repo)
    paths = {path.rstrip("/") for path in _glob(tools)["paths"]}
    assert {"linked_readme.md", "escape_link"} <= paths

    assert "Sample Repo" in tools["read"].invoke({"path": "linked_readme.md"})
    # 越界符号链接即使被列出，读取也必须被边界挡住
    assert tools["read"].invoke({"path": "escape_link"}).startswith("[tool_error]")


def test_read_skips_binary_instead_of_returning_mojibake(repo: Workspace) -> None:
    out = _tools(repo)["read"].invoke({"path": "assets/logo.bin"})
    assert "二进制" in out
    assert "\ufffd" not in out  # 不能把乱码塞进上下文


# ------------------------------------------- 回归 1：忽略判定误用绝对路径


def test_workspace_under_ignored_dir_name_is_still_visible(tmp_path: Path) -> None:
    """工作区路径里含 build 之类的名字时，内容不能被整体忽略。

    这是最凶的一种失败：完全静默，Agent 会以为工作区是空的。
    """
    root = tmp_path / "build" / "dist" / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "README.md").write_text("# hi\n", encoding="utf-8")
    (root / "pkg" / "mod.py").write_text("A = 1\n", encoding="utf-8")

    workspace = Workspace(root)
    tools = _tools(workspace)

    payload = _glob(tools)
    assert payload["total_matched"] > 0, "工作区自身路径含 build/dist 时不应被整体忽略"
    assert {path.rstrip("/") for path in payload["paths"]} >= {"README.md", "pkg/mod.py"}

    assert "共 0 项" not in tools["list_dir"].invoke({"path": "."})
    assert "共 2 项" in tools["list_dir"].invoke({"path": "."})


def test_ignore_check_only_considers_path_inside_workspace(repo: Workspace) -> None:
    assert repo.is_ignored(repo.root / "node_modules" / "x.js")
    assert not repo.is_ignored(repo.root / "src" / "main.py")
    # 工作区外一律不做忽略判定（越界由 resolve 负责报错）
    assert not repo.is_ignored(Path("/somewhere/build/elsewhere.txt"))


# --------------------------------------------- 回归 2：截断必须是显式的


def test_glob_reports_truncation_instead_of_silently_cutting(tmp_path: Path) -> None:
    total = MAX_LIST + 50
    (tmp_path / "pkg").mkdir()
    for index in range(total):
        (tmp_path / "pkg" / f"mod_{index:04d}.py").write_text(f"V = {index}\n", encoding="utf-8")

    payload = _glob(_tools(Workspace(tmp_path)), "**/*.py")

    assert payload["total_matched"] == total, "必须报告真实匹配总数"
    assert payload["returned"] == MAX_LIST
    assert payload["truncated"] is True
    assert payload["hint"], "截断时必须给出可操作的提示"
    assert len(payload["paths"]) == MAX_LIST


def test_glob_can_raise_limit_to_get_everything(tmp_path: Path) -> None:
    total = MAX_LIST + 50
    (tmp_path / "pkg").mkdir()
    for index in range(total):
        (tmp_path / "pkg" / f"mod_{index:04d}.py").write_text(f"V = {index}\n", encoding="utf-8")

    payload = _glob(_tools(Workspace(tmp_path)), "**/*.py", max_results=total + 100)
    assert payload["truncated"] is False
    assert payload["returned"] == total


def test_glob_rejects_non_positive_max_results(tmp_path: Path) -> None:
    assert (
        _tools(Workspace(tmp_path))["glob"]
        .invoke({"pattern": "*", "max_results": 0})
        .startswith("[tool_error]")
    )


def test_list_dir_reports_truncation_instead_of_silently_cutting(tmp_path: Path) -> None:
    total = MAX_LIST + 50
    for index in range(total):
        (tmp_path / f"f_{index:04d}.txt").write_text("x\n", encoding="utf-8")

    out = _tools(Workspace(tmp_path))["list_dir"].invoke({"path": "."})
    head, _, body = out.partition("\n")

    assert f"共 {total} 项" in head
    assert "仅显示前" in head, "表头必须声明被截断，否则模型会以为这就是全部"
    assert len(body.splitlines()) == MAX_LIST
