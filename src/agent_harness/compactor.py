"""上下文四级压缩:在预算内剪裁/摘要/归档历史,缓解长对话上下文膨胀。

四级策略(逐级升级,直至总量回到预算内):
  L1 结果剪裁    : 把单条最长的 tool/assistant 消息内容截为固定上限,保留前缀。
  L2 单条摘要    : 对最旧的 tool 消息用 summarizer 压成一条短提示。
  L3 滚动摘要    : 把连续的一段旧消息合并喂给 summarizer,收敛为一条摘要消息。
  L4 历史归档    : 若提供了 archive 回调,把被驱逐的旧消息交给外部存储,
                   原地放一条"已归档 n 条"指针消息。

说明:
- summarizer 为可注入的 LLM 摘要器;为保持离线可测,测试用确定性 fake。
- 该机制以 PreTurn hook 形态挂入循环,在每个模型调用前触发。
"""
from __future__ import annotations

from typing import Any, Callable

Summarizer = Callable[[str], str]

# 各预算默认值(字符)
_DEFAULT_MAX_CHARS = 40_000
_CHUNK = 8_000  # L1 单条截断上限
_ARCHIVE_BLOCK = 2  # L3/L4 每次处理的历史消息条数


def _char_count(messages: list[dict[str, Any]]) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages)


def _index_of_largest(messages: list[dict[str, Any]]):
    idx, size = -1, -1
    for i, m in enumerate(messages):
        c = str(m.get("content", ""))
        if m.get("role") in ("tool", "assistant") and len(c) > size:
            idx, size = i, len(c)
    return idx, size


def trim_message(messages: list[dict[str, Any]], index: int) -> None:
    """L1: 就地截断某条消息的内容(含标记不超过 _CHUNK)。"""
    content = str(messages[index].get("content", ""))
    if len(content) > _CHUNK:
        marker = "\n...[已按 L1 截断]"
        messages[index]["content"] = content[: _CHUNK - len(marker)] + marker


class ContextManager:
    def __init__(
        self,
        max_chars: int = _DEFAULT_MAX_CHARS,
        summarizer: Summarizer | None = None,
        archive: Callable[[list[dict[str, Any]]], None] | None = None,
    ) -> None:
        self._max_chars = max_chars
        self._summarizer = summarizer
        self._archive = archive
        self.total_evicted = 0
        self.summaries: list[str] = []

    def compact_once(self, messages: list[dict[str, Any]]) -> int:
        """执行一轮压缩,返回本轮的驱逐字符数;<=0 表示无需再压。"""
        if _char_count(messages) <= self._max_chars:
            return 0
        # L1: 截掉当前最长单条
        idx, size = _index_of_largest(messages)
        if idx >= 0 and size > _CHUNK:
            freed = size - _CHUNK
            trim_message(messages, idx)
            return freed
        # 需要语义压缩(L2/L3/L4)
        if self._summarizer is None and self._archive is None:
            return 0  # 无摘要能力且无归档,只能靠 L1
        if self._archive is not None:
            return self._archive_oldest_block(messages)  # L4
        return self._summarize_oldest(messages)  # L2/L3

    def compact(self, messages: list[dict[str, Any]]) -> int:
        """反复压缩直至回到预算。返回累计驱逐字符数。"""
        total = 0
        while True:
            freed = self.compact_once(messages)
            if freed <= 0:
                break
            total += freed
        return total

    def to_hook(self):
        def _hook(messages: list[dict[str, Any]]) -> None:
            self.compact(messages)

        return _hook

    # ---- 内部 ----
    def _evictable_index(self, messages):
        """返回可被驱逐的最旧 tool 消息下标;无则 -1。"""
        for i, m in enumerate(messages):
            if m.get("role") == "tool":
                return i
        return -1

    def _summarize_oldest(self, messages: list[dict[str, Any]]) -> int:
        """L2: 摘要最旧的 tool 消息。L3: 摘要一段(此处即以该消息为主体)。"""
        i = self._evictable_index(messages)
        if i < 0:
            return 0
        old = str(messages[i].get("content", ""))
        if not old or not self._summarizer:
            return 0
        summary = self._summarizer(old[:_CHUNK])
        self.summaries.append(summary)
        messages[i]["content"] = f"[已摘要] {summary}"
        return len(old) - len(messages[i]["content"])

    def _archive_oldest_block(self, messages: list[dict[str, Any]]) -> int:
        """L4: 取出最旧的一段历史交给外部归档,原地放指针。"""
        start = None
        n = 0
        for i, m in enumerate(messages):
            if m.get("role") in ("tool", "assistant"):
                if start is None:
                    start = i
                n += 1
                if n >= _ARCHIVE_BLOCK:
                    break
        if start is None:
            return 0
        block = messages[start : start + n]
        freed = sum(len(str(m.get("content", ""))) for m in block)
        self._archive(block)
        self.total_evicted += len(block)
        messages[start : start + n] = [
            {"role": "user", "content": f"[已归档 {n} 条旧消息,可查外部存储]"}
        ]
        return freed - 20