from pathlib import Path
from typing import Literal, Self

from pydantic import Field, PositiveInt, model_validator
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
    service_role: Literal["general", "classroom", "all"] = "all"
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
    worker_heartbeat_path: Path = Path("/tmp/pathlab-worker-heartbeat")
    worker_heartbeat_interval_seconds: PositiveInt = 10
    worker_heartbeat_stale_seconds: PositiveInt = 45
    serve_public_tiles: bool = False
    internal_file_redirects: bool = False
    multi_share_enabled: bool = True
    annotations_enabled: bool = False
    desktop_ome_dynamic_enabled: bool = True
    classroom_enabled: bool = False
    classroom_singleton: bool = False
    classroom_service_url: str = "http://classroom:8001"
    classroom_max_participants: int = Field(default=300, ge=1, le=2000)
    study_mode_enabled: bool = False
    study_coach_ai_enabled: bool = False
    study_max_learners: int = Field(default=500, ge=1, le=500)
    libvips_concurrency: PositiveInt = 1
    libvips_cache_max_mem_bytes: PositiveInt = 256 * 1024**2
    libvips_cache_max_files: PositiveInt = 128
    libvips_cache_max_operations: PositiveInt = 100
    tile_cache_root: Path = Path("./var/data/cache/ome-tiles")
    tile_cache_max_bytes: PositiveInt = 2 * 1024**3
    tile_cache_low_water_bytes: PositiveInt = 1792 * 1024**2
    tile_cache_max_temp_bytes: PositiveInt = 8 * 1024**2
    tile_cache_memory_bytes: PositiveInt = 256 * 1024**2
    tile_render_concurrency: PositiveInt = 2
    tile_service_url: str = "http://tile-service:8090"

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if self.tile_cache_low_water_bytes >= self.tile_cache_max_bytes:
            raise ValueError("Tile cache low-water mark must be below its maximum")
        if self.tile_cache_max_temp_bytes > 8 * 1024**2:
            raise ValueError("Tile cache temporary files must not exceed 8 MiB")
        if self.tile_cache_memory_bytes > 512 * 1024**2:
            raise ValueError("Tile cache memory must not exceed 512 MiB")
        if self.environment != "production":
            return self
        if self.service_role == "all":
            raise ValueError("Production rejects the combined service role")
        if (
            self.service_role == "classroom"
            and self.classroom_enabled
            and not self.classroom_singleton
        ):
            raise ValueError("Production classroom requires the declared singleton topology")
        secret = self.secret_key.strip()
        if len(secret.encode("utf-8")) < 32 or secret.casefold() in PRODUCTION_SECRET_PLACEHOLDERS:
            raise ValueError("Production requires a unique secret key of at least 32 bytes")
        if not self.secure_cookies:
            raise ValueError("Production requires secure cookies")
        return self
