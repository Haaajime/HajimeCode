"""集中加载 .env 中的模型配置。

默认对接 DeepSeek(OpenAI 兼容)。密钥只从环境变量/.env 读取,严禁硬编码进源码。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    max_tokens: int
    temperature: float


def get_settings(provider: str = "deepseek") -> Settings:
    """按 provider 组装配置。当前实现 DeepSeek;后续可为 Anthropic 扩展。

    Raises:
        RuntimeError: 缺少 API key 时提示,避免带空 key 发起请求。
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "未找到 DEEPSEEK_API_KEY,请在 agent-harness/.env 中填入后重试。"
        )
    return Settings(
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        max_tokens=int(os.environ.get("DEEPSEEK_MAX_TOKENS", "512")),
        temperature=float(os.environ.get("DEEPSEEK_TEMPERATURE", "0.3")),
    )