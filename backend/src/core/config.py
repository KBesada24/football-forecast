from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Football Forecast API"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_url: str
    test_database_url: str | None = None
    cors_origins: str = "http://localhost:3000"
    data_dir: Path = Field(default=Path("./data"))
    model_dir: Path = Field(default=Path("./models"))
    # Supabase CA certificate for sslmode=verify-full; unset for local development.
    database_ca_cert: Path | None = None

    @field_validator("data_dir", "model_dir", "database_ca_cert", mode="after")
    @classmethod
    def resolve_backend_path(cls, value: Path | None) -> Path | None:
        if value is None or value.is_absolute():
            return value
        return (BACKEND_DIR / value).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
