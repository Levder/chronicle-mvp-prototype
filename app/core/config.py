from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Verified Local Chronicle MVP"
    debug: bool = True
    database_url: str = "sqlite+aiosqlite:///./data/chronicle.db"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_api_mode: Literal["chat_completions", "agents"] = "chat_completions"
    openai_agent_session_id: str = ""

    solana_rpc_url: str = "https://api.devnet.solana.com"
    solana_network: str = "devnet"
    solana_private_key: str = ""
    solana_enabled: bool = False

    default_city: str = "irpin"

    # Routing thresholds (bootstrap — calibrate later)
    r_out_of_scope: float = 40.0
    e_quick: float = 75.0
    m_quick: float = 25.0
    e_deep: float = 45.0
    m_deep: float = 60.0
    critical_e: float = 35.0
    critical_c: float = 0.8


@lru_cache
def get_settings() -> Settings:
    return Settings()
