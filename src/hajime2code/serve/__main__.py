"""``hajime2code-web`` 入口：启动 Web 服务。"""

from __future__ import annotations

import argparse

import uvicorn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hajime2code-web",
        description="启动 Hajime2Code Web 控制台（FastAPI + SSE + 前端静态托管）。",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="开发模式：代码变更自动重启")
    args = parser.parse_args(argv)

    uvicorn.run(
        "hajime2code.serve.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
