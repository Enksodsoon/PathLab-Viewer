from pathlib import Path
from typing import Literal, Self

from pydantic import PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PRODUCTION_SECRET_PLACEHOLDERS = {
    "change-this-before-deployment",
    "replace-with-at-least-32-random-bytes",
    "generate-with-openssl-rand-hex-32",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PATHLAB_",
        env_file=".env",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./var/pathlab.sqlite3"
    data_root: Path = Path("./var/data")
    secret_key: str = "change-this-before-deployment"
    secure_cookies: bool = True
    session_hours: int = 12
    max_upload_bytes: int = 5 * 1024**3
    storage_cap_bytes: int = 120 * 1024**3
    tus_public_url: str = "/api/v1/uploads/"
    tus_internal_upload_dir: Path = Path("./var/tus")
    worker_stale_seconds: int = 300
    serve_public_tiles: bool = False
    libvips_concurrency: PositiveInt = 1
    libvips_cache_max_mem_bytes: PositiveInt = 256 * 1024**2
    libvips_cache_max_files: PositiveInt = 128
    libvips_cache_max_operations: PositiveInt = 100
    multi_share_enabled: bool = False

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if self.environment != "production":
            return self
        secret = self.secret_key.strip()
        if (
            len(secret.encode("utf-8")) < 32
            or secret.casefold() in PRODUCTION_SECRET_PLACEHOLDERS
        ):
            raise ValueError("Production requires a unique secret key of at least 32 bytes")
        if not self.secure_cookies:
            raise ValueError("Production requires secure cookies")
        return self
