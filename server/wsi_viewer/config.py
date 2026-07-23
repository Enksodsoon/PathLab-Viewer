from pathlib import Path
from typing import Literal, Self

from pydantic import PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PATHLAB_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./var/pathlab.sqlite3"
    data_root: Path = Path("./var/data")
    secret_key: str = "change-this-before-deployment"
    secure_cookies: bool = True
    expose_api_docs: bool = False
    session_hours: int = 12
    max_upload_bytes: int = 5 * 1024**3
    storage_cap_bytes: int = 120 * 1024**3
    tus_public_url: str = "/api/v1/uploads/"
    tus_internal_upload_dir: Path = Path("./var/tus")
    worker_stale_seconds: int = 300
    worker_heartbeat_path: Path = Path("/tmp/pathlab-worker-heartbeat")
    worker_heartbeat_interval_seconds: PositiveInt = 10
    worker_heartbeat_stale_seconds: PositiveInt = 45
    serve_public_tiles: bool = False
    libvips_concurrency: PositiveInt = 1
    libvips_cache_max_mem_bytes: PositiveInt = 256 * 1024**2
    libvips_cache_max_files: PositiveInt = 128
    libvips_cache_max_operations: PositiveInt = 100

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if self.environment != "production":
            return self

        normalized_secret = self.secret_key.strip().casefold()
        placeholder_markers = (
            "change-this",
            "replace-with",
            "generate-with",
            "not-used-in-production",
        )
        if len(self.secret_key.encode("utf-8")) < 32 or any(
            marker in normalized_secret for marker in placeholder_markers
        ):
            raise ValueError(
                "PATHLAB_SECRET_KEY must be a unique random value of at least 32 bytes"
            )
        if not self.secure_cookies:
            raise ValueError("Secure cookies are required in production")
        if self.expose_api_docs:
            raise ValueError("API documentation must remain disabled in production")
        if self.serve_public_tiles:
            raise ValueError("The production API must not serve public tiles directly")
        if not self.data_root.is_absolute() or not self.tus_internal_upload_dir.is_absolute():
            raise ValueError("Production data paths must be absolute")
        return self
