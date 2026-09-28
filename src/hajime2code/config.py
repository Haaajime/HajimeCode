"""集中配置：pydantic-settings 读取 .env / 环境变量。

密钥只从环境读取，严禁硬编码。项目内没有 .env 时会自动回退读取同级的
``HajimeCode/.env``，避免在两处重复维护密钥。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_files() -> tuple[Path, ...]:
    candidates = (
        _PROJECT_ROOT / ".env",
        _PROJECT_ROOT.parent / "HajimeCode" / ".env",
    )
    return tuple(path for path in candidates if path.is_file())


@dataclass(frozen=True)
class Pricing:
    """按百万 token 计的单价（元），用于成本核算。

    默认值仅为占位，引用成本结论前必须按官方定价校准。
    """

    cache_hit_per_mtok: float
    cache_miss_per_mtok: float
    output_per_mtok: float

    def cost_cny(
        self, *, cache_hit_tokens: int, cache_miss_tokens: int, output_tokens: int
    ) -> float:
        return (
            cache_hit_tokens * self.cache_hit_per_mtok
            + cache_miss_tokens * self.cache_miss_per_mtok
            + output_tokens * self.output_per_mtok
        ) / 1_000_000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # ---- 模型 ----
    api_key: str = Field(
        default="", validation_alias=AliasChoices("DEEPSEEK_API_KEY", "H2C_API_KEY")
    )
    base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("DEEPSEEK_BASE_URL", "H2C_BASE_URL"),
    )
    model_name: str = Field(
        default="deepseek-chat", validation_alias=AliasChoices("DEEPSEEK_MODEL", "H2C_MODEL")
    )
    temperature: float = 0.0
    max_tokens: int = Field(
        default=4096, validation_alias=AliasChoices("MAX_TOKENS", "H2C_MAX_TOKENS")
    )
    timeout_s: float = 120.0
    max_retries: int = 2

    # ---- 循环护栏 ----
    max_steps: int = Field(default=24, validation_alias=AliasChoices("MAX_STEPS", "H2C_MAX_STEPS"))
    max_attempts: int = Field(
        default=2, validation_alias=AliasChoices("MAX_ATTEMPTS", "H2C_MAX_ATTEMPTS")
    )

    # ---- 工作区 ----
    workspace: Path = Field(default_factory=Path.cwd)

    # ---- 成本单价（占位值，需按官方定价校准）----
    price_cache_hit_per_mtok: float = Field(
        default=0.2,
        validation_alias=AliasChoices("PRICE_CACHE_HIT_PER_MTOK", "H2C_PRICE_CACHE_HIT"),
    )
    price_cache_miss_per_mtok: float = Field(
        default=2.0,
        validation_alias=AliasChoices("PRICE_CACHE_MISS_PER_MTOK", "H2C_PRICE_CACHE_MISS"),
    )
    price_output_per_mtok: float = Field(
        default=3.0,
        validation_alias=AliasChoices("PRICE_OUTPUT_PER_MTOK", "H2C_PRICE_OUTPUT"),
    )

    @property
    def pricing(self) -> Pricing:
        return Pricing(
            cache_hit_per_mtok=self.price_cache_hit_per_mtok,
            cache_miss_per_mtok=self.price_cache_miss_per_mtok,
            output_per_mtok=self.price_output_per_mtok,
        )

    def require_api_key(self) -> str:
        key = self.api_key.strip()
        if not key:
            raise RuntimeError(
                "未找到 DEEPSEEK_API_KEY：请在 Hajime2Code/.env "
                "或 ../HajimeCode/.env 中填入后重试。"
            )
        return key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
