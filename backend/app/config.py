"""Central configuration loaded from environment variables (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://fleetguard:fleetguard@localhost:5432/fleetguard"
    )

    # LLM provider
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock").lower()
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    # Risk engine
    RISK_LEVEL_MEDIUM_THRESHOLD: float = float(os.getenv("RISK_LEVEL_MEDIUM_THRESHOLD", 40))
    RISK_LEVEL_HIGH_THRESHOLD: float = float(os.getenv("RISK_LEVEL_HIGH_THRESHOLD", 70))
    DEFAULT_CARGO_SETPOINT_C: float = float(os.getenv("DEFAULT_CARGO_SETPOINT_C", 4.0))

    # RAG
    SOP_MIN_SIMILARITY: float = float(os.getenv("SOP_MIN_SIMILARITY", 0.08))
    SOP_DOCS_DIR: str = os.getenv("SOP_DOCS_DIR", str(BASE_DIR / "sop_docs"))

    # Synthetic data
    SYNTHETIC_TRUCK_COUNT: int = int(os.getenv("SYNTHETIC_TRUCK_COUNT", 25))
    SEED_ON_STARTUP: bool = _bool(os.getenv("SEED_ON_STARTUP"), True)
    RANDOM_SEED: int = int(os.getenv("RANDOM_SEED", 42))

    # API
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", 8000))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
