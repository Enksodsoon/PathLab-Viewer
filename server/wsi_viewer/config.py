from pathlib import Path

from pydantic import PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_KEY_BYTES = 32
INSECURE_SECRET_KEYS = frozenset(
    {
        "change-this-before-deployment",
        "replace-with-at-least-32-random-bytes",
        "generate-with-openssl-rand-hex-32",
    }
)


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
    serve_public_tiles: bool = False
    libvips_concurrency: PositiveInt = 1
    libvips_cache_max_mem_bytes: PositiveInt = 256 * 1024**2
    libvips_cache_max_files: PositiveInt = 128
    libvips_cache_max_operations: PositiveInt = 100


def validate_runtime_security(settings: Settings) -> None:
    secret = settings.secret_key
    if secret in INSECURE_SECRET_KEYS or len(secret.encode("utf-8")) < MIN_SECRET_KEY_BYTES:
        raise RuntimeError(
            "PATHLAB_SECRET_KEY must contain at least 32 random bytes and must not use "
            "an example placeholder"
        )
