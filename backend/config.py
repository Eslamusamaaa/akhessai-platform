import os
import base64
import secrets
import warnings
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Resolve the directory that config.py lives in (always backend/)
_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, ".env"))

# Anything other than an explicit development environment is treated as production,
# where missing secrets are a hard error (no insecure fallbacks).
APP_ENV = os.getenv("APP_ENV", "production").lower()
IS_DEV = APP_ENV in ("development", "dev", "local")


def _required_secret(name: str, dev_factory):
    value = os.getenv(name)
    if value:
        return value
    if IS_DEV:
        warnings.warn(f"{name} is not set - using an ephemeral development value (lost on restart).")
        return dev_factory()
    raise RuntimeError(
        f"{name} must be set (see .env.example). For local development only, set APP_ENV=development."
    )


def _csv(name: str, default: str):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class Settings:
    # Absolute path -> seed.py and uvicorn always share the same SQLite file
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(_HERE, 'medical_assessment.db')}"
    )
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    # Get a key at https://openrouter.ai/keys
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

    JWT_SECRET: str = _required_secret("JWT_SECRET", lambda: secrets.token_hex(32))
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # PHI column encryption key: a valid Fernet key (urlsafe base64 of 32 random bytes)
    PHI_ENCRYPTION_KEY: str = _required_secret("PHI_ENCRYPTION_KEY", lambda: Fernet.generate_key().decode())

    # Browser origins allowed to call the API (the production frontend proxies /api, so it needs none)
    ALLOWED_ORIGINS = _csv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")

    # Demo accounts are OFF by default. Enable only for local demos, with your own password.
    SEED_DEMO_USERS: bool = os.getenv("SEED_DEMO_USERS", "false").lower() == "true"
    DEMO_PASSWORD: str = os.getenv("DEMO_PASSWORD", "")

    LLM_MODEL: str = os.getenv("LLM_MODEL", "google/gemini-2.5-flash")
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL",
        "paraphrase-multilingual-MiniLM-L12-v2"
    )


if len(Settings.JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must be at least 32 characters.")
try:
    if len(base64.urlsafe_b64decode(Settings.PHI_ENCRYPTION_KEY)) != 32:
        raise ValueError("wrong length")
    Fernet(Settings.PHI_ENCRYPTION_KEY.encode())
except Exception as exc:
    raise RuntimeError("PHI_ENCRYPTION_KEY must be a valid Fernet key (base64 of 32 bytes).") from exc

settings = Settings()
