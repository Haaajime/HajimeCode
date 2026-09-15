"""支持 `python -m agent_harness "提示词"` 的便捷入口。"""
from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())