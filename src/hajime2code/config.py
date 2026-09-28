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
#: 项目根目录（公开别名，供目录选择器等模块使用）。
PROJECT_ROOT = _PROJECT_ROOT


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

    # ---- 前端可选项 ----
    # 模型候选（逗号分隔）；实际列表 = 当前 model_name + 这里去重后的其余项。
    model_choices: str = Field(
        default="deepseek-chat,deepseek-reasoner",
        validation_alias=AliasChoices("H2C_MODEL_CHOICES", "MODEL_CHOICES"),
    )
    # 目录选择器的浏览边界。前端只能在这个根之下浏览。
    #
    # 注意区分：**工作目录本身不受此限制** —— 请求里直接给绝对路径可以指向任意存在的目录，
    # 这里约束的只是"用界面逐层浏览"的能力。设边界是因为浏览接口是 HTTP 端点，
    # 不限范围就等同于"任意列举本机目录"。
    #
    # 默认取**用户主目录**：再宽就没什么意义了，再窄则够不到自己的其他项目。
    # 想收紧或放宽都改 `H2C_BROWSE_ROOT`。
    browse_root: Path | None = Field(
        default=None, validation_alias=AliasChoices("H2C_BROWSE_ROOT", "BROWSE_ROOT")
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

    @property
    def available_models(self) -> list[str]:
        """可选模型：当前配置的模型排第一，其余候选去重追加。"""
        ordered = [self.model_name]
        for name in self.model_choices.split(","):
            candidate = name.strip()
            if candidate and candidate not in ordered:
                ordered.append(candidate)
        return ordered

    @property
    def resolved_browse_root(self) -> Path:
        """目录选择器的浏览根（解析后）。默认用户主目录，可用 ``H2C_BROWSE_ROOT`` 覆盖。"""
        if self.browse_root is not None:
            return self.browse_root.expanduser().resolve()
        try:
            return Path.home().resolve()
        except OSError:  # 极端环境下取不到家目录时退回项目上一级
            return _PROJECT_ROOT.parent

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
