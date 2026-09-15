"""文件工具(glob/read)单测 —— 全部离线,零 API 消耗。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_harness.file_tools import WorkspaceError, build_file_tools
from agent_harness.tools import ToolRegistry


@pytest.fixture
def workspace(tmp_path: Path):
    (tmp_path / "a.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (tmp_path / "src" / "util.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "src" / "ignored.pyc").write_bytes(b"\x00\x01")
    return tmp_path


@pytest.fixture
def reg(workspace: Path) -> ToolRegistry:
    reg = ToolRegistry()
    for t in build_file_tools(workspace):
        reg.register(t)
    return reg


def _disp(reg: ToolRegistry, name: str, **kwargs) -> str:
    return reg.dispatch(name, kwargs)


def test_glob_lists_matching_files(reg: ToolRegistry):
    out = json.loads(_disp(reg, "glob", pattern="*.txt"))
    assert out == ["a.txt"]


def test_glob_recursive(reg: ToolRegistry):
    out = json.loads(_disp(reg, "glob", pattern="*.py", recursive=True))
    assert out == ["src/main.py", "src/util.py"]


def test_glob_lists_src_entries(reg: ToolRegistry):
    out = json.loads(_disp(reg, "glob", pattern="src/*"))
    assert "src/main.py" in out and "src/util.py" in out
    assert "src" not in out  # 目录本身不应作为文件命中


def test_read_returns_content(reg: ToolRegistry):
    out = _disp(reg, "read", path="a.txt")
    assert "alpha" in out and "beta" in out and "gamma" in out


def test_read_with_offset_and_limit(reg: ToolRegistry):
    out = _disp(reg, "read", path="a.txt", offset=1, limit=1)
    assert "beta" in out and "alpha" not in out


def test_read_traversal_denied(reg: ToolRegistry):
    out = _disp(reg, "read", path="../../etc/passwd")
    assert "路径越界" in out and "password" not in out


def test_read_absolute_outside_base_denied(tmp_path, reg: ToolRegistry):
    outside = tmp_path.parent / "secret.txt"
    out = _disp(reg, "read", path=str(outside))
    assert "路径越界" in out


def test_read_directory_denied(tmp_path, reg: ToolRegistry):
    out = _disp(reg, "read", path="src")
    assert "不是可读文件" in out


def test_negative_offset_denied(reg: ToolRegistry):
    out = _disp(reg, "read", path="a.txt", offset=-1)
    assert "offset" in out


def test_relative_base_dir_builds(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    tools = build_file_tools(Path("."))
    assert {t.name for t in tools} == {"glob", "read"}