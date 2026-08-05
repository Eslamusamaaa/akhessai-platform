import os
import base64
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Resolve the directory that config.py lives in (always backend/)
_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, ".env"))

class Settings:
    # Absolute path → seed.py and uvicorn always share the same SQLite file
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(_HERE, 'medical_assessment.db')}"
    )
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    # No hardcoded fallback — must be set via environment / .env file.
    # Get a key at https://openrouter.ai/keys
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

    # Dev-only fallback secrets — override via .env for any shared or deployed environment.
    JWT_SECRET: str = os.getenv("JWT_SECRET", "64d62fdee9c9d31d9b79e522e9d2877f64b4d70587e33886788ec8a83ce81a73")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # PHI Column Encryption Key (must be Base64-encoded 32-byte key)
    # Dev-only fallback — override via .env for any shared or deployed environment.
    _raw_key = os.getenv("PHI_ENCRYPTION_KEY", "dEFnTHspERyvoROHuM2VZ-q0VG8Kk1TcsORQXKiQSkg=")
    try:
        # Decode and pad/slice to exactly 32 bytes for Fernet compatibility
        decoded = base64.urlsafe_b64decode(_raw_key)
        if len(decoded) < 32:
            decoded = decoded.ljust(32, b'\0')
        else:
            decoded = decoded[:32]
        PHI_ENCRYPTION_KEY: str = base64.urlsafe_b64encode(decoded).decode()
        # Validate
        Fernet(PHI_ENCRYPTION_KEY.encode())
    except Exception:
        # Fallback static key to prevent decryption mismatches across restarts
        PHI_ENCRYPTION_KEY: str = base64.urlsafe_b64encode(b"static_fallback_secret_32_bytes_").decode()

    LLM_MODEL: str = os.getenv("LLM_MODEL", "google/gemini-2.5-flash")
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL",
        "paraphrase-multilingual-MiniLM-L12-v2"
    )

settings = Settings()
