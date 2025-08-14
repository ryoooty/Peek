from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore

# --------- Paths ---------
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
DEFAULT_CONFIG_PATHS = (
    BASE_DIR / "config.yaml",
    BASE_DIR / "config.yml",
    BASE_DIR / "config.json",
)


# --------- Config Models ---------
class ModelTariff(BaseModel):
    # Конвертация usage → биллинговые токены (за 1000 LLM-токенов)
    input_per_1k: float = 1.0
    output_per_1k: float = 1.0
    cache_per_1k: float = 0.5


class SubscriberLimits(BaseModel):
    # Лимиты интерфейса и «избранного» по типам подписок
    chats_page_size: int = 10
    chats_pages_max: int = 2
    chars_page_size: int = 10
    chars_pages_max: int = 2
    fav_chats_max: int = 5
    fav_chars_max: int = 10


class SubsConfig(BaseModel):
    # Имена уровней подписки фиксированы: free/silver/gold (можно расширять)
    free: SubscriberLimits = Field(default_factory=SubscriberLimits)
    silver: SubscriberLimits = Field(
        default_factory=lambda: SubscriberLimits(
            chats_pages_max=4, chars_pages_max=4, fav_chats_max=10, fav_chars_max=20
        )
    )
    gold: SubscriberLimits = Field(
        default_factory=lambda: SubscriberLimits(
            chats_pages_max=6, chars_pages_max=6, fav_chats_max=20, fav_chars_max=40
        )
    )
    # Ночной бонус «токов» (бесплатных) по уровням
    nightly_toki_bonus: Dict[str, int] = Field(
        default_factory=lambda: {"free": 50000, "silver": 150000, "gold": 300000}
    )


class LimitsConfig(BaseModel):
    rate_limit_seconds: int = 3
    context_threshold_tokens: int = 6000
    proactive_enabled: bool = True
    request_timeout_seconds: int = 60
    proactive_cost_tokens: int = 0  # стоимость 1 проактивного после 2 free в биллинговых токенах
    live_split_nl_count: int = 3
    auto_compress_default: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    # Base
    bot_token: str
    admin_ids: List[int] = Field(default_factory=list)
    db_path: str = Field(default=str(BASE_DIR / "data.db"))
    env: str = Field(default="dev")
    log_level: str = Field(default="INFO")
    config_version: int = Field(default=1)


    # Provider
    deepseek_api_key: Optional[str] = None
    deepseek_base_url: str = "https://api.openai.com"
    default_model: str = "gpt-4o-mini"

    # Channel gate
    sub_channel_id: Optional[int] = None  # бот должен быть админом канала
    sub_channel_username: Optional[str] = None  # @username канала (по возможности)

    # Maintenance
    maintenance_mode: bool = False

    # Payments
    boosty_secret: Optional[str] = None
    donationalerts_secret: Optional[str] = None

    # APScheduler (persistent jobstore по желанию)
    apscheduler_persist: bool = False
    jobs_db_path: str = Field(default=str(BASE_DIR / "jobs.db"))

    # YAML overrides path (если нужен внешний конфиг)
    app_config_path: Optional[str] = Field(default=None)

    # Tariffs per model (переопределяем из YAML)
    model_tariffs: Dict[str, ModelTariff] = Field(
        default_factory=lambda: {
            "gpt-4o-mini": ModelTariff(
                input_per_1k=1.0, output_per_1k=1.0, cache_per_1k=0.5
            ),
            "gpt-4o": ModelTariff(
                input_per_1k=2.0, output_per_1k=2.0, cache_per_1k=1.0
            ),
            "deepseek-chat": ModelTariff(
                input_per_1k=14, output_per_1k=110, cache_per_1k=7
            ),
            "deepseek-reasoner": ModelTariff(
                input_per_1k=55, output_per_1k=219, cache_per_1k=14
            ),
        }
    )
    toki_spend_coeff: float = 1.0

    # Subscribers limits (из YAML можно поменять)
    subs: SubsConfig = Field(default_factory=SubsConfig)

    # Limits grouping
    limits: LimitsConfig = Field(default_factory=LimitsConfig)

    # Flags
    global_typing_enabled: bool = True

settings = Settings()
config_version = 1


# --------- Reload helpers ---------
_ReloadHooks: list = []


def register_reload_hook(fn) -> None:
    _ReloadHooks.append(fn)


def _load_external_config(path: Optional[str]) -> Dict[str, Any]:
    candidates: List[Path] = []
    if path:
        candidates.append(Path(path))
    else:
        env_path = os.getenv("APP_CONFIG")
        if env_path:
            candidates.append(Path(env_path))
        candidates.extend(DEFAULT_CONFIG_PATHS)
    for p in candidates:
        try:
            if not p.exists():
                continue
            if p.suffix.lower() in (".yml", ".yaml"):
                if yaml is None:
                    continue
                with open(p, "r", encoding="utf-8") as fh:
                    return yaml.safe_load(fh) or {}
            if p.suffix.lower() == ".json":
                with open(p, "r", encoding="utf-8") as fh:
                    return json.load(fh) or {}
        except Exception:
            continue
    return {}


def _apply_overrides(dst: Settings, overrides: Dict[str, Any]) -> None:
    if not overrides:
        return
    for k, v in overrides.items():
        if not hasattr(dst, k):
            continue
        cur = getattr(dst, k)
        if isinstance(cur, BaseModel) and isinstance(v, dict):
            # вложенные модели pydantic
            for nk, nv in v.items():
                if hasattr(cur, nk):
                    setattr(cur, nk, nv)
        else:
            setattr(dst, k, v)


def reload_settings() -> Settings:
    global config_version
    # перечитать ENV
    new = Settings()
    # подтянуть YAML/JSON
    overrides = _load_external_config(new.app_config_path)
    _apply_overrides(new, overrides)
    # применить inplace
    for k, v in new.model_dump().items():
        setattr(settings, k, v)
    config_version += 1
    # нотифицировать хуки
    for fn in list(_ReloadHooks):
        try:
            fn(settings)
        except Exception:
            continue
    return settings
