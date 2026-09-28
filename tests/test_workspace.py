from __future__ import annotations

from pathlib import Path

import pytest

from hajime2code.workspace import Workspace, WorkspaceError


def test_resolve_relative_path(workspace: Workspace) -> None:
    assert workspace.resolve("pkg/mod.py").name == "mod.py"


def test_relative_round_trip(workspace: Workspace) -> None:
    assert workspace.relative(workspace.resolve("README.md")) == "README.md"


def test_resolve_rejects_parent_escape(workspace: Workspace) -> None:
    with pytest.raises(WorkspaceError):
        workspace.resolve("../outside.py")


def test_resolve_rejects_absolute_escape(workspace: Workspace, tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError):
        workspace.resolve(str(tmp_path.parent / "elsewhere.py"))


def test_ignored_directories(workspace: Workspace) -> None:
    assert workspace.is_ignored(workspace.root / ".git" / "config")
    assert not workspace.is_ignored(workspace.root / "README.md")


def test_rejects_non_directory(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(WorkspaceError):
        Workspace(target)
