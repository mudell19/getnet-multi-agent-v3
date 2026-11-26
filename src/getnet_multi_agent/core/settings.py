"""Settings loaded from .env. The only place that reads configuration."""

from __future__ import annotations

from datetime import timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "data" / "crawl_cache"
STATE_DIR = ROOT / "data" / "state"
MERCHANTS_FILE = ROOT / "data" / "merchants.json"

LLM_TIMEOUT_S = 30
LAST_TURNS = 6
# Brazil has had no daylight saving time since 2019: a fixed offset avoids a tzdata dependency.
BRT = timezone(timedelta(hours=-3), "America/Sao_Paulo")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_MODEL_THINKING: str = "low"
    GEMINI_ROUTER_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_ROUTER_THINKING: str = "minimal"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"
    GEMINI_JUDGE_MODEL: str = "gemini-3.8-flash"
    GEMINI_JUDGE_THINKING: str = "high"
    PRICE_FLASH_INPUT_PER_M: float = 0.75
    PRICE_FLASH_OUTPUT_PER_M: float = 3.75
    PRICE_LITE_INPUT_PER_M: float = 0.30
    PRICE_LITE_OUTPUT_PER_M: float = 2.50
    PRICE_EMBEDDING_PER_M: float = 0.20
    PRICE_SEARCH_PER_1K: float = 14.0
    JWT_SECRET: str = ""
    JWT_ISSUER: str = "getnet-multi-agent"
    JWT_AUDIENCE: str = "getnet-multi-agent-api"
    PSEUDONYM_KEY: str = ""
    MAX_MESSAGE_CHARS: int = 2000
    RAG_TOP_K: int = 6
    RAG_MAX_PAGES: int = 80
    RAG_MIN_SIMILARITY: float = 0.62
    MAX_TOOL_ITERATIONS: int = 3
    MAX_SUPERVISOR_ITERATIONS: int = 3
    REQUEST_TOKEN_BUDGET: int = 30000
    LLM_MODE: Literal["live", "stub"] = "live"


@lru_cache
def get_settings() -> Settings:
    return Settings()
