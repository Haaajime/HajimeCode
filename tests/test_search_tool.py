"""search 工具：内容定位的覆盖度与诚实性。

两个判据，与 test_fs_coverage.py 同一套纪律：
1. 覆盖：该找到的跨目录 / 跨文件命中一条不漏，被忽略目录与二进制文件要排除。
2. 诚实：超限必须显式 truncated=true 并给出真实 total_matched，不静默少给；
   跳过了多少文件要报出来，因为"无命中"的结论只在已扫描范围内成立。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hajime2code.tools.fs import MAX_SEARCH_LINE_CHARS, MAX_SEARCH_RESULTS, build_fs_tools
from hajime2code.workspace import Workspace

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _search(workspace: Workspace, **kwargs: Any) -> dict[str, Any]:
    tools = {tool.name: tool for tool in build_fs_tools(workspace)}
    return json.loads(tools["search"].invoke(kwargs))


def _raw(workspace: Workspace, **kwargs: Any) -> str:
    tools = {tool.name: tool for tool in build_fs_tools(workspace)}
    return tools["search"].invoke(kwargs)


@pytest.fixture
def repo() -> Workspace:
    return Workspace(FIXTURE)


# ---------------------------------------------------------------- 覆盖


def test_finds_matches_a_deeply_nested_file(repo: Workspace) -> None:
    """4 层深嵌套的文件也要能被搜到。"""
    payload = _search(repo, pattern="深三层")
    hits = {(match["file"], match["line"]) for match in payload["matches"]}
    assert ("docs/deep/nested/more/level3.md", 1) in hits
    assert payload["truncated"] is False


def test_finds_matches_by_content_across_directories(repo: Workspace) -> None:
    """按内容定位 —— 这正是"先搜再读"相对"猜文件名"的价值所在。"""
    payload = _search(repo, pattern=r"class Config")
    files = {match["file"] for match in payload["matches"]}
    assert "src/core/models.py" in files
    assert payload["files_with_matches"] >= 1


def test_matches_non_ascii_and_spaced_paths(repo: Workspace) -> None:
    files = {match["file"] for match in _search(repo, pattern="42")["matches"]}
    assert "src/中文模块/常量.py" in files

    note = _search(repo, pattern="note")
    assert "dir with spaces/note file.txt" in {match["file"] for match in note["matches"]}


def test_file_pattern_filters_to_python_only(repo: Workspace) -> None:
    payload = _search(repo, pattern="run", file_pattern="*.py")
    assert payload["matches"], "应能在 .py 里找到 run"
    assert all(match["file"].endswith(".py") for match in payload["matches"])

    md = _search(repo, pattern="使用指南", file_pattern="*.py")
    assert md["total_matched"] == 0


def test_path_argument_narrows_scope(repo: Workspace) -> None:
    payload = _search(repo, pattern="Config", path="src/core")
    assert {match["file"] for match in payload["matches"]} == {
        "src/core/engine.py",
        "src/core/models.py",
    }


def test_searching_a_single_file(repo: Workspace) -> None:
    payload = _search(repo, pattern="slugify", path="src/utils/helpers.py")
    assert payload["total_matched"] == 1


def test_ignore_case(repo: Workspace) -> None:
    assert _search(repo, pattern="sample repo")["total_matched"] == 0
    assert _search(repo, pattern="sample repo", ignore_case=True)["total_matched"] > 0


def test_context_lines_include_surrounding_lines(repo: Workspace) -> None:
    payload = _search(repo, pattern="def slugify", context_lines=1)
    entry = payload["matches"][0]
    assert "context" in entry
    assert len(entry["context"]) == 2  # 上一行 + 命中行


# ---------------------------------------------------------------- 排除


def test_excludes_ignored_directories(tmp_path: Path) -> None:
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "a.py").write_text("NEEDLE = 1\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("NEEDLE = 1\n", encoding="utf-8")

    payload = _search(Workspace(tmp_path), pattern="NEEDLE")
    assert {match["file"] for match in payload["matches"]} == {"keep/a.py"}


def test_skips_binary_and_reports_the_gap(repo: Workspace) -> None:
    """二进制文件要被跳过且计数上报；不能把乱码混进结果。"""
    payload = _search(repo, pattern="binary")
    assert payload["matches"] == []
    assert payload["files_skipped_binary"] >= 1
    assert payload["hint"], "跳过了文件就必须说明结论的适用范围"


def test_never_returns_mojibake(repo: Workspace) -> None:
    for match in _search(repo, pattern=".")["matches"]:
        assert "\ufffd" not in match["text"]


def test_rejects_path_outside_workspace(repo: Workspace) -> None:
    assert _raw(repo, pattern="root", path="../../etc").startswith("[tool_error]")


def test_rejects_missing_path(repo: Workspace) -> None:
    assert _raw(repo, pattern="x", path="nope/").startswith("[tool_error]")


# ---------------------------------------------------------------- 诚实


def test_reports_truncation_instead_of_silently_cutting(tmp_path: Path) -> None:
    total = MAX_SEARCH_RESULTS + 25
    (tmp_path / "pkg").mkdir()
    for index in range(total):
        (tmp_path / "pkg" / f"f_{index:03d}.py").write_text("NEEDLE = 1\n", encoding="utf-8")

    payload = _search(Workspace(tmp_path), pattern="NEEDLE")

    assert payload["total_matched"] == total, "必须报告真实命中总数"
    assert payload["returned"] == MAX_SEARCH_RESULTS
    assert payload["truncated"] is True
    assert "max_results" in payload["hint"]


def test_can_raise_limit_to_get_everything(tmp_path: Path) -> None:
    total = MAX_SEARCH_RESULTS + 25
    (tmp_path / "pkg").mkdir()
    for index in range(total):
        (tmp_path / "pkg" / f"f_{index:03d}.py").write_text("NEEDLE = 1\n", encoding="utf-8")

    payload = _search(Workspace(tmp_path), pattern="NEEDLE", max_results=total + 10)
    assert payload["truncated"] is False
    assert payload["returned"] == total


def test_clips_pathologically_long_lines(tmp_path: Path) -> None:
    """压缩过的单行文件不能把上下文撑爆。"""
    (tmp_path / "bundle.js").write_text(
        "var a=1;" + "x" * 5000 + "NEEDLE" + "y" * 5000, encoding="utf-8"
    )
    match = _search(Workspace(tmp_path), pattern="NEEDLE")["matches"][0]
    assert len(match["text"]) <= MAX_SEARCH_LINE_CHARS + 1


def test_reports_scanned_file_count(repo: Workspace) -> None:
    payload = _search(repo, pattern="Sample Repo")
    assert payload["files_scanned"] > 0
    assert payload["files_with_matches"] >= 1


# ---------------------------------------------------------------- 参数校验


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"pattern": "("}, "正则"),
        ({"pattern": "x", "max_results": 0}, "max_results"),
        ({"pattern": "x", "context_lines": -1}, "context_lines"),
        ({"pattern": ""}, "pattern"),
    ],
)
def test_rejects_bad_arguments(repo: Workspace, kwargs: dict[str, Any], fragment: str) -> None:
    out = _raw(repo, **kwargs)
    assert out.startswith("[tool_error]")
    assert fragment in out
