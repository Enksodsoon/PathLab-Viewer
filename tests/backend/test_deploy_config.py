from pathlib import Path

EXPECTED_COMPOSE_SERVICES = ("caddy", "api", "tusd", "worker")
EXPECTED_LOGGING_LINES = [
    "      driver: json-file",
    "      options:",
    '        max-size: "10m"',
    '        max-file: "3"',
]


def test_all_services_use_bounded_json_file_logging() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    lines = compose.splitlines()
    services_start = lines.index("services:") + 1
    services_end = lines.index("volumes:")
    service_starts = [
        (index, line.removeprefix("  ").removesuffix(":"))
        for index, line in enumerate(lines[services_start:services_end], services_start)
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":")
    ]

    assert tuple(name for _, name in service_starts) == EXPECTED_COMPOSE_SERVICES

    for position, (start, service_name) in enumerate(service_starts):
        end = (
            service_starts[position + 1][0]
            if position + 1 < len(service_starts)
            else services_end
        )
        service_lines = lines[start + 1 : end]
        assert "    logging:" in service_lines, f"{service_name} missing logging config"

        logging_start = service_lines.index("    logging:") + 1
        logging_lines: list[str] = []
        for line in service_lines[logging_start:]:
            if not line or len(line) - len(line.lstrip()) <= 4:
                break
            logging_lines.append(line)

        assert logging_lines == EXPECTED_LOGGING_LINES, service_name


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

    fallback = (
        "\n\thandle {\n\t\troot * /srv\n\t\ttry_files {path} /index.html"
        "\n\t\tfile_server\n\t}\n"
    )
    assert fallback in caddyfile
    assert caddyfile.index("handle @backend") < caddyfile.index(fallback)


def test_production_deploy_is_manual_serial_and_main_only() -> None:
    workflow = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "name: production" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow


def test_production_deploy_uses_restricted_ssh_credentials() -> None:
    workflow = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8"
    )

    assert "secrets.OCI_DEPLOY_KEY" in workflow
    assert "secrets.OCI_KNOWN_HOSTS" in workflow
    assert "vars.OCI_HOST" in workflow
    assert "vars.OCI_USER" in workflow
    assert '"deploy $GITHUB_SHA"' in workflow
    assert "appleboy/ssh-action" not in workflow


def test_release_script_has_atomic_swap_health_check_and_rollback() -> None:
    script = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")

    assert "git ls-remote" in script
    assert "refs/heads/main" in script
    assert "docker compose config --quiet" in script
    assert "docker compose build" in script
    assert "systemctl reload pathlab-viewer" in script
    assert "mv \"${LIVE_DIR}\" \"${ROLLBACK_DIR}\"" in script
    assert "mv \"${STAGE_DIR}\" \"${LIVE_DIR}\"" in script
    assert "curl --fail" in script
    assert "rollback_release" in script
    assert "flock" in script


def test_release_script_preserves_environment_and_never_touches_data() -> None:
    script = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")

    assert 'install -m 600 "${LIVE_DIR}/deploy/.env"' in script
    assert "/srv/pathlab/data" not in script
    assert "docker compose down" not in script
