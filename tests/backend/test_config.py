import pytest
from pydantic import ValidationError
from wsi_viewer.config import Settings

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


def test_annotations_are_disabled_by_default_and_accept_an_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PATHLAB_ANNOTATIONS_ENABLED", raising=False)

    assert Settings(_env_file=None).annotations_enabled is False

    monkeypatch.setenv("PATHLAB_ANNOTATIONS_ENABLED", "true")
    assert Settings(_env_file=None).annotations_enabled is True


def test_multi_share_is_enabled_by_default_and_accepts_the_kill_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PATHLAB_MULTI_SHARE_ENABLED", raising=False)

    assert Settings(_env_file=None).multi_share_enabled is True

    monkeypatch.setenv("PATHLAB_MULTI_SHARE_ENABLED", "false")
    assert Settings(_env_file=None).multi_share_enabled is False


def test_desktop_ome_dynamic_is_enabled_by_default_and_has_a_kill_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PATHLAB_DESKTOP_OME_DYNAMIC_ENABLED", raising=False)
    assert Settings(_env_file=None).desktop_ome_dynamic_enabled is True

    monkeypatch.setenv("PATHLAB_DESKTOP_OME_DYNAMIC_ENABLED", "false")
    assert Settings(_env_file=None).desktop_ome_dynamic_enabled is False


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


def test_tile_cache_limits_are_ordered_and_bounded() -> None:
    settings = Settings(_env_file=None)
    assert settings.tile_cache_max_bytes == 2 * 1024**3
    assert settings.tile_cache_low_water_bytes == 1792 * 1024**2
    assert settings.tile_cache_memory_bytes == 256 * 1024**2

    with pytest.raises(ValueError, match="low-water"):
        Settings(
            _env_file=None,
            tile_cache_max_bytes=100,
            tile_cache_low_water_bytes=100,
        )
    with pytest.raises(ValueError, match="temporary"):
        Settings(_env_file=None, tile_cache_max_temp_bytes=8 * 1024**2 + 1)
    with pytest.raises(ValueError, match="memory"):
        Settings(_env_file=None, tile_cache_memory_bytes=512 * 1024**2 + 1)
