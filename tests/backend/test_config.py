import pytest
from pydantic import ValidationError
from wsi_viewer.config import Settings, validate_runtime_security
from wsi_viewer.preflight import main as run_preflight

LIMIT_ENVIRONMENT = {
    "PATHLAB_LIBVIPS_CONCURRENCY": "3",
    "PATHLAB_LIBVIPS_CACHE_MAX_MEM_BYTES": "536870912",
    "PATHLAB_LIBVIPS_CACHE_MAX_FILES": "64",
    "PATHLAB_LIBVIPS_CACHE_MAX_OPERATIONS": "50",
}


def test_libvips_limits_have_conservative_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in LIMIT_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.libvips_concurrency == 1
    assert settings.libvips_cache_max_mem_bytes == 256 * 1024**2
    assert settings.libvips_cache_max_files == 128
    assert settings.libvips_cache_max_operations == 100


def test_libvips_limits_accept_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in LIMIT_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)

    assert settings.libvips_concurrency == 3
    assert settings.libvips_cache_max_mem_bytes == 536870912
    assert settings.libvips_cache_max_files == 64
    assert settings.libvips_cache_max_operations == 50


@pytest.mark.parametrize(
    "field",
    (
        "libvips_concurrency",
        "libvips_cache_max_mem_bytes",
        "libvips_cache_max_files",
        "libvips_cache_max_operations",
    ),
)
@pytest.mark.parametrize("value", (0, -1))
def test_libvips_limits_reject_non_positive_values(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


@pytest.mark.parametrize(
    "secret_key",
    (
        "",
        "short-secret",
        "change-this-before-deployment",
        "replace-with-at-least-32-random-bytes",
        "generate-with-openssl-rand-hex-32",
    ),
)
def test_runtime_rejects_missing_short_or_placeholder_secret_keys(secret_key: str) -> None:
    settings = Settings(_env_file=None, secret_key=secret_key)

    with pytest.raises(RuntimeError, match="PATHLAB_SECRET_KEY"):
        validate_runtime_security(settings)


def test_runtime_accepts_a_long_non_placeholder_secret_key() -> None:
    settings = Settings(_env_file=None, secret_key="a" * 64)

    validate_runtime_security(settings)


def test_deployment_preflight_requires_explicit_secret_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PATHLAB_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="must be set explicitly"):
        run_preflight()


def test_deployment_preflight_accepts_explicit_strong_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATHLAB_SECRET_KEY", "b" * 64)

    run_preflight()
