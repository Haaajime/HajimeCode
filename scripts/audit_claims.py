"""筛出注释与 docstring 里"承重的断言"，供人工逐条核实。

为什么需要它：注释里最危险的不是写得难看，而是**把机制讲错了**。
读者（包括未来的自己）会照着学，所以每一条"因为 X 所以 Y"都该能被验证。
本脚本只负责**筛选**，不负责判定——它把候选挑出来，人来决定怎么验。

只挑三类真正承重的断言，不抓所有含因果词的句子：

1. 因果类：否则 / 一旦 / 就会 / 会导致 —— 声称"A 不做 B 就会出问题"
2. 依赖库行为类：create_agent / add_messages / StaticFiles 等 —— 声称某库会怎样
3. 契约类：必须先 / 必须唯一 —— 声称某条件不满足就会被拒

用法：
    uv run python scripts/audit_claims.py            # 列出全部候选
    uv run python scripts/audit_claims.py fd         # 只看文件名含 fd 的
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
import tokenize

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAN_DIRS = ("src", "tests")
EXCLUDE_PARTS = {"fixtures", "node_modules", ".venv"}

CAUSAL = re.compile(r"否则|一旦|不然|就会|才会|会导致|必然")
CONTRACT = re.compile(r"必须先|必须唯一|必须走|必须拦|必须报")
LIBRARY = re.compile(
    r"create_agent|add_messages|StateGraph|ToolNode|bind_tools|"
    r"LangGraph|LangChain|StaticFiles|broadcast|reducer"
)

RULES = (
    ("因果", CAUSAL),
    ("契约", CONTRACT),
    ("库行为", LIBRARY),
)


def iter_python_files() -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for base in SCAN_DIRS:
        for path in sorted((ROOT / base).rglob("*.py")):
            if EXCLUDE_PARTS & set(path.relative_to(ROOT).parts):
                continue
            found.append(path)
    return found


def comment_lines(path: pathlib.Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type == tokenize.COMMENT:
                found.append((token.start[0], token.string.strip()))
    return found


def docstring_lines(path: pathlib.Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if not doc:
                continue
            start = node.body[0].lineno
            for offset, line in enumerate(doc.splitlines()):
                found.append((start + offset, line.strip()))
    return found


def main() -> int:
    needle = sys.argv[1] if len(sys.argv) > 1 else ""
    total = 0

    for path in iter_python_files():
        relative = path.relative_to(ROOT).as_posix()
        if needle and needle not in relative:
            continue

        rows: list[tuple[int, str, str, str]] = []
        for kind, items in (("注释", comment_lines(path)), ("docstring", docstring_lines(path))):
            for lineno, body in items:
                if not body:
                    continue
                for label, pattern in RULES:
                    if pattern.search(body):
                        rows.append((lineno, kind, label, body))
                        break

        if not rows:
            continue

        print(f"\n{relative}")
        for lineno, kind, label, body in sorted(rows):
            total += 1
            print(f"  {lineno:>4} [{label}] {kind}：{body[:96]}")

    print(f"\n共 {total} 条候选。挑出其中'如果错了会误导'的，逐条做实验核实。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
