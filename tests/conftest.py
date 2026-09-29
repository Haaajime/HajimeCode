"""共用 fixture。

所有 fixture 都显式构造依赖，不读取本机 .env，保证离线、可复现、零 API 消耗。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hajime2code.config import Settings
from hajime2code.workspace import Workspace

# tests/fixtures/ 下是被测数据（模拟真实仓库，里面自然也有 tests/test_*.py）。
# 必须拦住 pytest 的自动收集，否则会把样例仓库的测试当成本项目测试来跑。
collect_ignore_glob = ["fixtures/*"]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        api_key="test-key",
        base_url="http://127.0.0.1:1",
        model_name="test-model",
        workspace=Path("."),
        max_steps=6,
        max_attempts=2,
        price_cache_hit_per_mtok=1.0,
        price_cache_miss_per_mtok=2.0,
        price_output_per_mtok=4.0,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    return Workspace(tmp_path)
