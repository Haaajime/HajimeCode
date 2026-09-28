from __future__ import annotations

import json
from typing import Any

from hajime2code.tools.fs import build_fs_tools
from hajime2code.workspace import Workspace


def _tools(workspace: Workspace) -> dict[str, Any]:
    return {tool.name: tool for tool in build_fs_tools(workspace)}


def test_exposes_expected_tool_set(workspace: Workspace) -> None:
    assert set(_tools(workspace)) == {"read", "list_dir", "glob", "search", "write", "edit"}


def test_read_returns_header_and_content(workspace: Workspace) -> None:
    out = _tools(workspace)["read"].invoke({"path": "pkg/mod.py"})
    assert "pkg/mod.py" in out
    assert "return a + b" in out


def test_read_rejects_escape(workspace: Workspace) -> None:
    out = _tools(workspace)["read"].invoke({"path": "../../etc/hosts"})
    assert out.startswith("[tool_error]")


def test_read_reports_missing_file(workspace: Workspace) -> None:
    out = _tools(workspace)["read"].invoke({"path": "nope.py"})
    assert out.startswith("[tool_error]")


def test_list_dir(workspace: Workspace) -> None:
    out = _tools(workspace)["list_dir"].invoke({})
    assert "pkg/" in out
    assert "README.md" in out


def test_glob_returns_json_object_with_metadata(workspace: Workspace) -> None:
    payload = json.loads(_tools(workspace)["glob"].invoke({"pattern": "**/*.py"}))
    assert payload["paths"] == ["pkg/mod.py"]
    assert payload["total_matched"] == 1
    assert payload["truncated"] is False


def test_write_creates_file_and_parents(workspace: Workspace) -> None:
    out = _tools(workspace)["write"].invoke({"path": "notes/a.txt", "content": "hello"})
    assert "已写入" in out
    assert (workspace.root / "notes" / "a.txt").read_text(encoding="utf-8") == "hello"


def test_write_rejects_escape(workspace: Workspace) -> None:
    out = _tools(workspace)["write"].invoke({"path": "../evil.txt", "content": "x"})
    assert out.startswith("[tool_error]")
    assert not (workspace.root.parent / "evil.txt").exists()


def test_edit_replaces_unique_snippet(workspace: Workspace) -> None:
    tools = _tools(workspace)
    out = tools["edit"].invoke({"path": "pkg/mod.py", "old_string": "a + b", "new_string": "a - b"})
    assert "替换 1 处" in out
    assert "a - b" in (workspace.root / "pkg" / "mod.py").read_text(encoding="utf-8")


def test_edit_reports_missing_snippet(workspace: Workspace) -> None:
    out = _tools(workspace)["edit"].invoke(
        {"path": "pkg/mod.py", "old_string": "不存在", "new_string": "x"}
    )
    assert "未找到" in out


def test_edit_refuses_ambiguous_snippet_then_allows_replace_all(workspace: Workspace) -> None:
    tools = _tools(workspace)
    tools["write"].invoke({"path": "dup.txt", "content": "x\nx\n"})

    refused = tools["edit"].invoke({"path": "dup.txt", "old_string": "x", "new_string": "y"})
    assert "不唯一" in refused

    applied = tools["edit"].invoke(
        {"path": "dup.txt", "old_string": "x", "new_string": "y", "replace_all": True}
    )
    assert "替换 2 处" in applied
    assert (workspace.root / "dup.txt").read_text(encoding="utf-8") == "y\ny\n"


def test_edit_rejects_escape(workspace: Workspace) -> None:
    out = _tools(workspace)["edit"].invoke(
        {"path": "../outside.txt", "old_string": "a", "new_string": "b"}
    )
    assert out.startswith("[tool_error]")
