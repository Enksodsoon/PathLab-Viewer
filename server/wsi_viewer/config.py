from pathlib import Path

from pydantic import PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PATHLAB_", env_file=".env", extra="ignore")

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
    multi_share_enabled: bool = False
    libvips_concurrency: PositiveInt = 1
    libvips_cache_max_mem_bytes: PositiveInt = 256 * 1024**2
    libvips_cache_max_files: PositiveInt = 128
    libvips_cache_max_operations: PositiveInt = 100
