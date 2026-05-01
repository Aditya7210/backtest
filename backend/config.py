"""Application configuration via pydantic-settings. Reads from .env / environment."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration knobs — read from env vars or .env file."""

    # MongoDB
    MONGO_URI: str = "mongodb://mongodb:27017/algo_trading"

    # Zerodha
    ZERODHA_API_KEY: str = ""
    ZERODHA_API_SECRET: str = ""
    ZERODHA_ACCESS_TOKEN: str = ""
    ZERODHA_TOKEN_DATE: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173"
    ENV_FILE_PATH: str = ".env"

    # Backtesting
    BACKTEST_WORKER_COUNT: int = 1
    TASK_STORE_PATH: str = "/app/data/task_store.json"

    # Live Market collector controls (E-34)
    LM_EQUITY_UNIVERSE: str = "NIFTY500_PLUS_FNO"
    LM_EQUITY_UNIVERSE_PATH: str = ""
    LM_OPTION_EXPIRY_COUNT: int = 1
    LM_STRIKES_AROUND_ATM: int = 0
    LM_COLLECT_EQUITIES: bool = True
    LM_COLLECT_OPTIONS: bool = True
    LM_COLLECT_VIX: bool = True
    LM_COLLECT_INDEX_SPOT_TOKENS: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
