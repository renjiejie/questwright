"""Application settings loaded from environment / .env file.

Required env vars are enforced at startup so that mis-configuration fails fast
rather than at the first LLM call.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2].parent  # repo root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM providers (required at runtime; optional for local non-LLM tests) ---
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key for story generation")
    DEEPSEEK_API_KEY: str = Field(default="", description="DeepSeek API key for world auditing")

    # --- Embedding provider (decoupled from chat LLM) ---
    # Default targets Aliyun DashScope (OpenAI-compatible), text-embedding-v4 with
    # dim=1536 to stay compatible with the existing dnd_rag Chroma collection.
    EMBEDDING_API_KEY: str = Field(
        default="", description="API key for embedding provider (DashScope by default)"
    )
    EMBEDDING_BASE_URL: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="OpenAI-compatible base URL for the embedding endpoint",
    )
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-v4", description="Embedding model name"
    )
    EMBEDDING_DIM: int = Field(
        default=1536,
        ge=1,
        description="Embedding output dimension; must match the Chroma collection",
    )

    # --- Storage paths ---
    DATABASE_URL: str = Field(
        default=f"sqlite+aiosqlite:///{PROJECT_ROOT}/data/dnd.db",
        description="Async SQLAlchemy DSN for the business DB",
    )
    CHROMA_PATH: str = Field(
        default=str(PROJECT_ROOT / "data" / "chroma"),
        description="Local Chroma persistent client path",
    )
    CHROMA_COLLECTION: str = Field(default="dnd_rag", description="Default Chroma collection name")
    SRD_DATA_PATH: str = Field(
        default=str(PROJECT_ROOT / "vendor" / "5e-database" / "src" / "2014" / "en"),
        description="Path to 5e-bits/5e-database SRD JSON files",
    )
    UPLOAD_DIR: str = Field(
        default=str(PROJECT_ROOT / "data" / "uploads"),
        description="Directory for uploaded world bible source files",
    )
    PARSED_DIR: str = Field(
        default=str(PROJECT_ROOT / "data" / "parsed"),
        description="Directory for parsed source artifacts",
    )

    # --- Runtime knobs ---
    APP_ENV: str = Field(default="dev", description="dev|staging|prod")
    LOG_LEVEL: str = Field(default="INFO")
    EMBEDDING_BATCH_SIZE: int = Field(default=64, ge=1)
    RETRIEVAL_TOP_K: int = Field(default=8, ge=1)
    MAX_UPLOAD_BYTES: int = Field(default=20 * 1024 * 1024, ge=1)

    @field_validator("APP_ENV")
    @classmethod
    def _check_env(cls, v: str) -> str:
        if v not in {"dev", "staging", "prod"}:
            raise ValueError(f"APP_ENV must be dev|staging|prod, got {v!r}")
        return v

    def require_llm_keys(self) -> None:
        """Call before performing any live LLM operation.

        Settings construction stays permissive so unit tests / migrations don't
        need real keys; production code that actually talks to LLMs must call
        this guard explicitly.
        """
        missing = [
            name
            for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY")
            if not getattr(self, name)
        ]
        if missing:
            raise RuntimeError(
                f"Missing required env vars for LLM operations: {', '.join(missing)}. "
                "Add them to .env (see .env.example)."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
