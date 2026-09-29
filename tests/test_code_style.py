"""代码风格守卫：注释与 docstring 一律写成纯文本，不用 Markdown 标记。

为什么要有这条守卫：注释是读给人看的纯文本。写成 Markdown 的反引号
（用双反引号包标识符那种写法）和粗体（用星号包起来那种写法）之后，
读者要先在脑子里翻译一层才能看懂，纯属增加噪音。这个毛病在本项目里
蔓延过 32 个文件、两百多处，所以用测试把它钉住。

检查范围严格限定为注释与 docstring —— 不检查普通字符串字面量：
字符串里的内容可能是给渲染层或给模型的数据，规则不同
（例如 TypeScript 的模板字符串本来就合法使用反引号）。
"""

from __future__ import annotations

import ast
import re
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCAN_DIRS = ("src", "tests")
EXCLUDE_PARTS = {"fixtures", "node_modules", ".venv"}
WEB_SRC = ROOT / "web" / "src"
TS_SUFFIXES = {".ts", ".tsx"}

# 双反引号（RST 行内代码）—— 出现即违规，不存在误判
DOUBLE_BACKTICK = re.compile(r"``")
SINGLE_BACKTICK = re.compile(r"(?<!`)`[^`\n]+`(?!`)")
# Markdown 粗体：要有一对星号，且中间不含斜杠与星号，
# 以免误伤 glob 模式这类合法内容
BOLD = re.compile(r"\*\*[^*/\n]*\*\*")

RULES = (
    ("双反引号", DOUBLE_BACKTICK),
    ("单反引号", SINGLE_BACKTICK),
    ("Markdown 粗体", BOLD),
)


def _find(sections: list[tuple[str, list[tuple[int, str]]]]) -> list[str]:
    offenders: list[str] = []
    for kind, items in sections:
        for lineno, body in items:
            for label, pattern in RULES:
                hit = pattern.search(body)
                if hit:
                    offenders.append(f"  {kind} 第 {lineno} 行含{label}：{hit.group(0)}")
    return offenders


def _fail(path: Path, offenders: list[str]) -> None:
    assert not offenders, (
        f"{path.relative_to(ROOT)} 的注释 / docstring 里出现了 Markdown 标记，"
        f"请改写成纯文本：\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------- Python


def _python_files() -> list[Path]:
    found: list[Path] = []
    for base in SCAN_DIRS:
        for path in sorted((ROOT / base).rglob("*.py")):
            if EXCLUDE_PARTS & set(path.relative_to(ROOT).parts):
                continue
            found.append(path)
    return found


def _docstrings(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                found.append((node.body[0].lineno, doc))
    return found


def _comments(path: Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type == tokenize.COMMENT:
                found.append((token.start[0], token.string))
    return found


@pytest.mark.parametrize("path", _python_files(), ids=lambda item: str(item.relative_to(ROOT)))
def test_python_comments_and_docstrings_are_plain_text(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = _find([("docstring", _docstrings(tree)), ("注释", _comments(path))])
    _fail(path, offenders)


# ---------------------------------------------------------------- TypeScript


def _ts_files() -> list[Path]:
    if not WEB_SRC.is_dir():
        return []
    return sorted(path for path in WEB_SRC.rglob("*") if path.suffix in TS_SUFFIXES)


def _ts_comment_lines(path: Path) -> list[tuple[int, str]]:
    """按行判断是否注释行。

    这是行级启发式，不是真正的 TS 词法分析：只把以两条斜杠、斜杠星号
    或星号开头的行当注释。之所以够用，是因为标记出现在代码行里往往是
    合法用法（模板字符串），本就不该由这条规则管。
    """
    found: list[tuple[int, str]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("//", "/*", "*")):
            found.append((index, stripped))
    return found


@pytest.mark.parametrize("path", _ts_files(), ids=lambda item: str(item.relative_to(ROOT)))
def test_ts_comments_are_plain_text(path: Path) -> None:
    offenders = _find([("注释", _ts_comment_lines(path))])
    _fail(path, offenders)
