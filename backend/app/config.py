from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Loads secrets from backend/.env (preferred) or the project-root .env."""

    app_name: str = "UrbanTwin API"
    database_url: str
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    upload_dir: str = "uploads"
    # Shared staff token for the government dashboard. Empty = auth disabled (lab only).
    staff_token: str = ""
    # Pretrained image model for duplicate checks. "none" = always use the average hash.
    embedding_model: str = "facebook/dinov2-small"
    # Optional hosted "AI second opinion" providers. Empty key = provider unavailable.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"  # check Google's current model list; names change
    hf_api_token: str = ""
    hf_detection_model: str = ""  # you must choose an object-detection model id; no default is assumed
    hf_api_url: str = "https://api-inference.huggingface.co/models/{model}"
    ai_timeout_seconds: float = 30.0
    # Create tables on startup. Prefer `alembic upgrade head`; this is a dev convenience.
    auto_create_tables: bool = False

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", PROJECT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
