from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    gemini_model: str = "gemini-3.5-flash"  # must appear in `python -m scripts.list_gemini_models`; names change, override with GEMINI_MODEL in .env
    # Optional local model through Ollama (https://ollama.com). Off unless both are set, e.g. OLLAMA_URL=http://localhost:11434 and a vision model you pulled.
    ollama_url: str = ""
    ollama_model: str = ""
    ollama_timeout_seconds: float = 180.0  # local models can be slow on CPU
    hf_api_token: str = ""
    hf_model: str = "Qwen/Qwen2.5-VL-3B-Instruct"  # a vision-language model offered by Hugging Face Inference Providers; change with HF_MODEL in .env
    hf_api_url: str = "https://router.huggingface.co/v1"
    ai_timeout_seconds: float = 30.0
    # Folder with the built frontend (frontend/dist). Set in the Docker image so one server serves app + API. Empty = API only.
    frontend_dist: str = ""
    # Create tables on startup. Prefer `alembic upgrade head`; this is a dev convenience.
    auto_create_tables: bool = False

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", PROJECT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def _driver_prefix(cls, value: str) -> str:
        """Hosted databases give postgres:// or postgresql:// URLs; this app uses the psycopg 3 driver."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
