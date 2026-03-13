from dotenv import load_dotenv
import os

load_dotenv()


class Config:
    # ── API ────────────────────────────────────────────────
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_PREFIX: str = "/api"

    # ── LLM ────────────────────────────────────────────────
    LLM_API_URL: str = os.getenv("LLM_API_URL", "https://api.mistral.ai/v1/chat/completions")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "mistral-small-latest")
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "30"))
    USE_MOCK_LLM: bool = os.getenv("USE_MOCK_LLM", "true").lower() == "true"

    # ── NER ────────────────────────────────────────────────
    USE_NER: bool = os.getenv("USE_NER", "true").lower() == "true"
    NER_FALLBACK_TO_REGEX: bool = True

    # ── Маскирование ───────────────────────────────────────
    TOKEN_FORMAT: str = os.getenv("TOKEN_FORMAT", "bracket")
    SCAN_LLM_OUTPUT: bool = os.getenv("SCAN_LLM_OUTPUT", "true").lower() == "true"

    # ── Сессии ─────────────────────────────────────────────
    SESSION_TTL_SECONDS: int = int(os.getenv("SESSION_TTL", "3600"))

    # ── Аудит ──────────────────────────────────────────────
    AUDIT_LOG_FILE: str = os.getenv("AUDIT_LOG_FILE", "audit.log")
    AUDIT_ENABLED: bool = os.getenv("AUDIT_ENABLED", "true").lower() == "true"

    # ── Детекторы ──────────────────────────────────────────
    ENABLED_PII_TYPES: set = {
        "PHONE", "EMAIL", "PASSPORT", "SNILS", "INN",
        "CARD", "ACCOUNT", "DATE", "PERSON", "ADDRESS",
    }
    MIN_CONFIDENCE: float = float(os.getenv("MIN_CONFIDENCE", "0.5"))


config = Config()