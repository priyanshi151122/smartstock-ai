"""Application configuration.

All runtime configuration comes from environment variables so that no secret or
machine specific path is ever hard-coded in the source tree.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime settings loaded from the environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SmartStock AI"
    app_version: str = "1.0.0"
    environment: Literal["development", "production", "test"] = "development"

    # ------------------------------------------------------------------ storage
    # SQLite for local development. The DATABASE_URL is parsed by app.db.database
    # and any PostgreSQL DSN (postgresql://...) is routed to the psycopg adapter.
    database_url: str = Field(default="sqlite:///./data/smartstock.db")
    data_dir: str = Field(default=str(PROJECT_ROOT / "data"))

    # ------------------------------------------------------------------- uploads
    max_upload_mb: int = 10
    max_upload_rows: int = 200_000
    allowed_upload_extensions: tuple[str, ...] = (".csv", ".xlsx", ".xlsm")

    # --------------------------------------------------------------- forecasting
    min_history_days_for_ml: int = 42
    default_horizon_days: int = 14
    default_model: str = "auto"
    service_level_z: float = 1.65  # ~95% cycle service level

    # ------------------------------------------------------------------- server
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    )
    serve_frontend: bool = True

    @field_validator("max_upload_mb")
    @classmethod
    def _sane_upload_limit(cls, value: int) -> int:
        if not 1 <= value <= 200:
            raise ValueError("MAX_UPLOAD_MB must be between 1 and 200")
        return value

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        return path

    @property
    def upload_dir(self) -> Path:
        return self.data_path / "uploads"

    @property
    def report_dir(self) -> Path:
        return self.data_path / "reports"

    @property
    def frontend_dist(self) -> Path:
        return PROJECT_ROOT / "frontend" / "dist"

    def ensure_directories(self) -> None:
        for directory in (self.data_path, self.upload_dir, self.report_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
