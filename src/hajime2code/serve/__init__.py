"""服务化层：把图执行暴露为 REST + SSE，供前端控制台消费。"""

from __future__ import annotations

from .app import create_app

__all__ = ["create_app"]
