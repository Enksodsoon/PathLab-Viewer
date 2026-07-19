from pathlib import Path


def test_tusd_uses_pathlab_data_owner() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    tusd_service = compose.split("\n  tusd:\n", maxsplit=1)[1].split(
        "\n  worker:\n", maxsplit=1
    )[0]

    assert 'user: "10001:10001"' in tusd_service


def test_api_creates_runtime_directories_before_migrations() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    api_service = compose.split("\n  api:\n", maxsplit=1)[1].split(
        "\n  tusd:\n", maxsplit=1
    )[0]

    command = api_service.split("command:", maxsplit=1)[1].split(
        "environment:", maxsplit=1
    )[0]
    assert "mkdir -p /data/database /data/tus" in command
    assert command.index("mkdir -p") < command.index("alembic upgrade head")


def test_caddy_spa_fallback_does_not_rewrite_api_paths() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")

    fallback = "\n\thandle {\n\t\troot * /srv\n\t\ttry_files {path} /index.html\n\t\tfile_server\n\t}\n"
    assert fallback in caddyfile
    assert caddyfile.index("handle @backend") < caddyfile.index(fallback)
