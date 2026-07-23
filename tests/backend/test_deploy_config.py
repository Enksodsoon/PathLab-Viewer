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
            service_starts[position + 1][0] if position + 1 < len(service_starts) else services_end
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
    tusd_service = compose.split("\n  tusd:\n", maxsplit=1)[1].split("\n  worker:\n", maxsplit=1)[0]

    assert 'user: "10001:10001"' in tusd_service


def test_conversion_resource_limits_are_worker_only() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    caddy_service = compose.split("\n  caddy:\n", maxsplit=1)[1].split("\n  api:\n", maxsplit=1)[0]
    api_service = compose.split("\n  api:\n", maxsplit=1)[1].split("\n  tusd:\n", maxsplit=1)[0]
    tusd_service = compose.split("\n  tusd:\n", maxsplit=1)[1].split("\n  worker:\n", maxsplit=1)[0]
    worker_service = compose.split("\n  worker:\n", maxsplit=1)[1].split(
        "\nvolumes:\n", maxsplit=1
    )[0]
    expected = (
        "PATHLAB_LIBVIPS_CONCURRENCY",
        "PATHLAB_LIBVIPS_CACHE_MAX_MEM_BYTES",
        "PATHLAB_LIBVIPS_CACHE_MAX_FILES",
        "PATHLAB_LIBVIPS_CACHE_MAX_OPERATIONS",
        "VIPS_CONCURRENCY",
        "MALLOC_ARENA_MAX",
    )

    for name in expected:
        assert name in worker_service
        assert name not in caddy_service
        assert name not in api_service
        assert name not in tusd_service

    assert 'VIPS_CONCURRENCY: "1"' in worker_service
    assert 'MALLOC_ARENA_MAX: "2"' in worker_service
    assert "mem_limit: 6g" in worker_service
    assert "cpus: 1.50" in worker_service


def test_worker_has_heartbeat_healthcheck_and_graceful_stop_period() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    worker_service = compose.split("\n  worker:\n", maxsplit=1)[1].split(
        "\nvolumes:\n", maxsplit=1
    )[0]

    assert 'test: ["CMD", "pathlab-worker-healthcheck"]' in worker_service
    assert "interval: 15s" in worker_service
    assert "timeout: 5s" in worker_service
    assert "retries: 3" in worker_service
    assert "start_period: 30s" in worker_service
    assert "stop_grace_period: 30m" in worker_service


def test_example_environment_documents_libvips_overrides() -> None:
    example = Path("deploy/.env.example").read_text(encoding="utf-8")

    assert "PATHLAB_LIBVIPS_CONCURRENCY=1" in example
    assert "PATHLAB_LIBVIPS_CACHE_MAX_MEM_BYTES=268435456" in example
    assert "PATHLAB_LIBVIPS_CACHE_MAX_FILES=128" in example
    assert "PATHLAB_LIBVIPS_CACHE_MAX_OPERATIONS=100" in example


def test_api_creates_runtime_directories_before_migrations() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    api_service = compose.split("\n  api:\n", maxsplit=1)[1].split("\n  tusd:\n", maxsplit=1)[0]

    command = api_service.split("command:", maxsplit=1)[1].split("environment:", maxsplit=1)[0]
    assert "mkdir -p /data/database /data/tus" in command
    assert command.index("mkdir -p") < command.index("alembic upgrade head")


def test_api_reconciles_storage_after_migration_before_startup() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    api_service = compose.split("\n  api:\n", maxsplit=1)[1].split("\n  tusd:\n", maxsplit=1)[0]
    command = api_service.split("command:", maxsplit=1)[1].split("environment:", maxsplit=1)[0]

    assert "pathlab-admin reconcile-storage" in command
    assert command.index("alembic upgrade head") < command.index("pathlab-admin reconcile-storage")
    assert command.index("pathlab-admin reconcile-storage") < command.index("uvicorn")


def test_caddy_spa_fallback_does_not_rewrite_api_paths() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")

    fallback = (
        '\n\thandle {\n\t\troot * /srv\n\t\theader Cache-Control "no-cache"'
        "\n\t\ttry_files {path} /index.html"
        "\n\t\tfile_server\n\t}\n"
    )
    assert fallback in caddyfile
    assert caddyfile.index("handle @backend") < caddyfile.index(fallback)


def test_caddy_cache_policy_separates_tiles_assets_html_and_api() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")
    uploads = caddyfile.split("handle @uploads {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    backend = caddyfile.split("handle @backend {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    tiles = caddyfile.split("handle_path /tiles/* {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    assets = caddyfile.split("handle /assets/* {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    spa = caddyfile.split("\thandle {\n", maxsplit=1)[1].split("\n\t}", maxsplit=1)[0]

    assert 'header Cache-Control "no-store"' in uploads
    assert 'header Cache-Control "no-store"' in backend
    assert 'header Cache-Control "public, max-age=31536000, s-maxage=60, immutable"' in tiles
    assert 'header X-Content-Type-Options "nosniff"' in tiles
    assert 'header Cache-Control "public, max-age=31536000, immutable"' in assets
    assert "root * /srv" in assets
    assert "reverse_proxy" not in assets
    assert 'header Cache-Control "no-cache"' in spa
    assert caddyfile.index("handle /assets/*") < caddyfile.index("\thandle {\n")


def test_production_deploy_is_manual_serial_and_main_only() -> None:
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "name: production" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow


def test_production_deploy_uses_temporary_oci_bastion_session() -> None:
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")

    assert "secrets.OCI_CONFIG" in workflow
    assert "secrets.OCI_API_PRIVATE_KEY" in workflow
    assert "secrets.OCI_BASTION_KNOWN_HOSTS" in workflow
    assert "deploy/scripts/deploy-via-bastion.sh" in workflow
    assert "secrets.OCI_DEPLOY_KEY" not in workflow
    assert "vars.OCI_HOST" not in workflow


def test_bastion_client_uses_ephemeral_key_and_always_deletes_session() -> None:
    script = Path("deploy/scripts/deploy-via-bastion.sh").read_text(encoding="utf-8")

    assert "ssh-keygen" in script
    assert "oci bastion session create-managed-ssh" in script
    assert "oci bastion session list" in script
    assert "--wait-for-state" not in script
    assert "trap cleanup_bastion_session EXIT" in script
    assert "oci bastion session delete" in script
    assert "StrictHostKeyChecking=yes" in script
    assert "deploy ${TARGET_SHA}" in script


def test_bastion_target_has_no_interactive_deployment_access() -> None:
    script = Path("deploy/scripts/configure-bastion-target.sh").read_text(encoding="utf-8")

    assert "pathlab-deploy" in script
    assert "DisableForwarding yes" in script
    assert "PermitTTY no" in script
    assert "PasswordAuthentication no" in script
    assert "ForceCommand /usr/local/sbin/pathlab-viewer-deploy-entrypoint" in script
    assert "NOPASSWD: /usr/local/sbin/pathlab-viewer-deploy" in script


def test_shell_scripts_are_checked_out_with_unix_line_endings() -> None:
    attributes = Path(".gitattributes").read_text(encoding="utf-8")

    assert "*.sh text eol=lf" in attributes


def test_release_script_has_atomic_swap_health_check_and_rollback() -> None:
    script = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")

    assert "git ls-remote" in script
    assert "refs/heads/main" in script
    assert "docker compose config --quiet" in script
    assert "docker compose build" in script
    assert "systemctl reload pathlab-viewer" in script
    assert 'mv "${LIVE_DIR}" "${ROLLBACK_DIR}"' in script
    assert 'mv "${STAGE_DIR}" "${LIVE_DIR}"' in script
    assert "curl --fail" in script
    assert "rollback_release" in script
    assert "flock" in script
    assert 'cat "${LIVE_DIR}/.pathlab-release"' in script
    assert 'git -C "${LIVE_DIR}" rev-parse HEAD' not in script


def test_release_script_preserves_environment_and_never_touches_data() -> None:
    script = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")

    assert 'install -m 600 "${LIVE_DIR}/deploy/.env"' in script
    assert "/srv/pathlab/data" not in script
    assert "docker compose down" not in script


def test_release_script_interlocks_before_worker_disruption() -> None:
    script = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")

    helper_call = 'deployment_check "${STAGE_DIR}"'
    first_check = script.index(helper_call)
    stop_worker = script.index("docker compose stop worker")
    second_check = script.index(helper_call, first_check + 1)
    swap = script.index('mv "${LIVE_DIR}" "${ROLLBACK_DIR}"')

    assert first_check < stop_worker < second_check < swap
    assert "docker compose start worker" in script
    assert "OLD_WORKER_STOPPED" in script
    assert "restart_old_worker" in script
    assert "/srv/pathlab/data" not in script
    assert "docker compose down" not in script


def test_worker_healthcheck_console_command_is_registered() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'pathlab-worker-healthcheck = "wsi_viewer.worker_health:main"' in pyproject


def test_ci_avoids_duplicate_feature_branch_runs() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "push:\n    branches: [main]" in workflow
    assert "pull_request:" in workflow
    assert "group: ci-${{ github.workflow }}-${{" in workflow
    assert "github.event.pull_request.number || github.ref" in workflow
    assert "cancel-in-progress: true" in workflow


def test_arm64_container_builds_use_separate_github_caches() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    for scope in ("backend", "web"):
        assert f"--cache-from type=gha,scope={scope}" in workflow
        assert f"--cache-to type=gha,mode=max,scope={scope}" in workflow
