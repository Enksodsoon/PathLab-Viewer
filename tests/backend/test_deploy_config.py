from pathlib import Path

EXPECTED_COMPOSE_SERVICES = ("caddy", "api", "tile-service", "tusd", "worker")
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


def test_conversion_resource_limits_are_worker_and_tile_service_only() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    caddy_service = compose.split("\n  caddy:\n", maxsplit=1)[1].split(
        "\n  api:\n", maxsplit=1
    )[0]
    api_service = compose.split("\n  api:\n", maxsplit=1)[1].split(
        "\n  tile-service:\n", maxsplit=1
    )[0]
    tile_service = compose.split("\n  tile-service:\n", maxsplit=1)[1].split(
        "\n  tusd:\n", maxsplit=1
    )[0]
    tusd_service = compose.split("\n  tusd:\n", maxsplit=1)[1].split(
        "\n  worker:\n", maxsplit=1
    )[0]
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
        assert name in tile_service
        assert name not in caddy_service
        assert name not in api_service
        assert name not in tusd_service

    assert 'VIPS_CONCURRENCY: "1"' in worker_service
    assert 'MALLOC_ARENA_MAX: "2"' in worker_service
    assert "mem_limit: 6g" in worker_service
    assert "cpus: 1.50" in worker_service


def test_backend_image_smoke_imports_every_production_runtime() -> None:
    dockerfile = Path("deploy/Dockerfile.backend").read_text(encoding="utf-8")
    requirements = Path("deploy/backend-requirements.txt").read_text(encoding="utf-8")

    assert "pillow==12.3.0" in requirements
    assert "from PIL import Image" in dockerfile
    assert "import wsi_viewer.main, wsi_viewer.tile_service, wsi_viewer.worker" in dockerfile


def test_delivery_optimized_oci_resource_budget_prioritizes_caddy() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    caddy_service = compose.split("\n  caddy:\n", maxsplit=1)[1].split(
        "\n  api:\n", maxsplit=1
    )[0]
    api_service = compose.split("\n  api:\n", maxsplit=1)[1].split(
        "\n  tile-service:\n", maxsplit=1
    )[0]
    worker_service = compose.split("\n  worker:\n", maxsplit=1)[1].split(
        "\nvolumes:\n", maxsplit=1
    )[0]

    assert "mem_limit: 256m" in caddy_service
    assert "cpus: 1.25" in caddy_service
    assert "cpu_shares: 1024" in caddy_service
    assert "--workers 1" in api_service
    assert "mem_limit: 512m" in api_service
    assert "cpus: 0.50" in api_service
    assert "cpu_shares: 1024" in api_service
    assert "cpu_shares: 256" in worker_service


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


def test_annotation_feature_flag_is_explicitly_default_off_in_deployment_examples() -> None:
    root_example = Path(".env.example").read_text(encoding="utf-8")
    deploy_example = Path("deploy/.env.example").read_text(encoding="utf-8")
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")

    assert "PATHLAB_ANNOTATIONS_ENABLED=false" in root_example
    assert "PATHLAB_ANNOTATIONS_ENABLED=false" in deploy_example
    assert (
        'PATHLAB_ANNOTATIONS_ENABLED: "${PATHLAB_ANNOTATIONS_ENABLED:-false}"'
        in compose
    )


def test_annotation_operations_runbook_and_bundle_budget_are_ci_contracts() -> None:
    guide = Path("docs/architecture/ADMIN_ANNOTATIONS.md")
    package = Path("apps/web/package.json").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    web_job = workflow.split("\n  web:\n", maxsplit=1)[1].split(
        "\n  containers:\n", maxsplit=1
    )[0]

    assert guide.is_file()
    guide_text = guide.read_text(encoding="utf-8")
    for required in (
        "PATHLAB_ANNOTATIONS_ENABLED=false",
        "25,000",
        "256 KiB",
        "30-day",
        "backup",
        "rollback",
        "admin-only",
    ):
        assert required in guide_text
    assert '"check:annotation-bundle"' in package
    assert "fetch-depth: 0" in web_job
    assert "github.event.pull_request.base.sha" in web_job
    assert "github.event.before" in web_job
    assert "git worktree add --detach" in web_job
    assert "vite build --config vite.config.ts --manifest" in web_job
    assert (
        'pnpm --dir apps/web check:annotation-bundle -- '
        '--baseline "$PATHLAB_BUNDLE_BASELINE"'
    ) in web_job


def test_annotation_benchmark_explains_the_actual_paginated_api_query_shape() -> None:
    benchmark = Path("scripts/benchmark_annotations.py").read_text(encoding="utf-8")

    assert "select(Annotation)" in benchmark
    assert "select(func.count(Annotation.id))" in benchmark
    assert ".order_by(Annotation.created_at, Annotation.id)" in benchmark
    assert ".offset(PAGE_OFFSET)" in benchmark
    assert ".limit(PAGE_SIZE)" in benchmark
    assert '"literal_binds": True' in benchmark
    assert '"activeCountQueryPlan"' in benchmark
    assert '"activePageQueryPlan"' in benchmark
    assert '"viewportCountQueryPlan"' in benchmark
    assert '"viewportPageQueryPlan"' in benchmark


def test_ci_runs_the_bounded_annotation_browser_matrix() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "\n  browser:\n" in workflow
    browser_job = workflow.split("\n  browser:\n", maxsplit=1)[1].split(
        "\n  containers:\n", maxsplit=1
    )[0]
    assert "timeout-minutes: 15" in browser_job
    assert "playwright install --with-deps chromium firefox webkit" in browser_job
    assert "PLAYWRIGHT_PORT: \"5217\"" in browser_job
    assert "e2e/annotation-responsive.spec.ts" in browser_job
    assert "e2e/shared-viewer-responsive.spec.ts" in browser_job
    assert "--workers=2" in browser_job


def test_api_creates_runtime_directories_before_migrations() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    api_service = compose.split("\n  api:\n", maxsplit=1)[1].split(
        "\n  tile-service:\n", maxsplit=1
    )[0]

    command = api_service.split("command:", maxsplit=1)[1].split(
        "environment:", maxsplit=1
    )[0]
    assert "mkdir -p /data/database /data/tus" in command
    assert command.index("mkdir -p") < command.index("alembic upgrade head")


def test_api_reconciles_storage_after_migration_before_startup() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    api_service = compose.split("\n  api:\n", maxsplit=1)[1].split(
        "\n  tile-service:\n", maxsplit=1
    )[0]
    command = api_service.split("command:", maxsplit=1)[1].split(
        "environment:", maxsplit=1
    )[0]

    assert "pathlab-admin reconcile-storage" in command
    assert command.index("alembic upgrade head") < command.index(
        "pathlab-admin reconcile-storage"
    )
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


def test_caddy_serves_isolated_individual_tiles_and_preserves_route_cache_headers() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    uploads = caddyfile.split("handle @uploads {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    backend = caddyfile.split("handle @backend {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    assets = caddyfile.split("handle /assets/* {", maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    spa = caddyfile.split("\thandle {\n", maxsplit=1)[1].split("\n\t}", maxsplit=1)[0]

    assert 'header Cache-Control "no-store"' in uploads
    assert 'header ?Cache-Control "no-store"' in backend
    assert "handle_path /tiles/*" in caddyfile
    assert "root * /pathlab-individual" in caddyfile
    assert (
        "${PATHLAB_DATA_DIR:-/srv/pathlab/data}/delivery/individual:"
        "/pathlab-individual:ro"
    ) in compose
    assert "/pathlab-individual" in compose
    assert "${PATHLAB_DATA_DIR:-/srv/pathlab/data}/public:/pathlab-public:ro" in compose
    assert "${PATHLAB_DATA_DIR:-/srv/pathlab/data}/private:/pathlab-private:ro" in compose
    assert "PATHLAB_INTERNAL_FILE_REDIRECTS: \"true\"" in compose
    assert "/pathlab-data" not in compose
    assert "header X-Accel-Redirect *" in caddyfile
    assert "rewrite * {rp.header.X-Accel-Redirect}" in caddyfile
    assert "${PATHLAB_DATA_DIR:-/srv/pathlab/data}/tus:/data/tus" in compose
    assert 'header Cache-Control "public, max-age=31536000, immutable"' in assets
    assert "root * /srv" in assets
    assert "reverse_proxy" not in assets
    assert 'header Cache-Control "no-cache"' in spa
    assert caddyfile.index("handle /assets/*") < caddyfile.index("\thandle {\n")


def test_dynamic_tile_service_is_internal_bounded_and_authorized_by_api() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")
    api = compose.split("\n  api:\n", maxsplit=1)[1].split(
        "\n  tile-service:\n", maxsplit=1
    )[0]
    tile_service = compose.split("\n  tile-service:\n", maxsplit=1)[1].split(
        "\n  tusd:\n", maxsplit=1
    )[0]

    assert 'command: ["pathlab-tiles"]' in tile_service
    assert 'expose: ["8090"]' in tile_service
    assert "\n    ports:" not in tile_service
    assert (
        "${PATHLAB_DATA_DIR:-/srv/pathlab/data}/originals:/data/originals:ro"
        in tile_service
    )
    assert "pathlab-tile-cache:/cache/ome-tiles" in tile_service
    assert "PATHLAB_TILE_CACHE_MAX_BYTES:-2147483648" in tile_service
    assert "PATHLAB_TILE_CACHE_LOW_WATER_BYTES:-1879048192" in tile_service
    assert "PATHLAB_TILE_RENDER_CONCURRENCY:-2" in tile_service
    assert "pathlab-internal" in api
    assert "pathlab-internal" in tile_service
    assert "internal: true" in compose
    assert "pathlab-tile-cache:" in compose
    assert (
        "install -d -o pathlab -g pathlab -m 700 /cache/ome-tiles"
        in Path("deploy/Dockerfile.backend").read_text(encoding="utf-8")
    )

    assert "@dynamic_delivery header X-Accel-Redirect /_pathlab_ome/*" in caddyfile
    assert "reverse_proxy tile-service:8090" in caddyfile
    assert "@direct_dynamic path /_pathlab_ome/*" in caddyfile
    assert "respond @direct_dynamic 404" in caddyfile


def test_caddy_flushes_classroom_sse_without_buffering() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")
    assert "@classroom_events path" in caddyfile
    classroom = caddyfile.split("handle @classroom_events", maxsplit=1)[1].split(
        "@backend", maxsplit=1
    )[0]
    assert "flush_interval -1" in classroom
    assert 'Cache-Control "no-store"' in classroom


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
    assert "group: production-control" in workflow


def test_capacity_certification_is_manual_protected_and_serialized_with_deploys() -> None:
    workflow = Path(".github/workflows/capacity-certification.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "CERTIFY_PRODUCTION_300" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "name: production" in workflow
    assert "group: production-control" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "timeout-minutes: 60" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "schedule:" not in workflow
    assert "secrets.LOAD_TEST_PUBLIC_ID" not in workflow
    assert "secrets.LOAD_TEST_ADMIN_SLIDE_ID" not in workflow
    assert "secrets.LOAD_TEST_ADMIN_PASSWORD" in workflow
    assert "vars.PRODUCTION_BASE_URL" in workflow
    assert "tests/load/viewer.js" not in workflow
    assert "deploy/scripts/run-capacity-certification.sh" in workflow
    assert "capacity-fixture.spec.ts" in Path(
        "deploy/scripts/run-capacity-certification.sh"
    ).read_text(encoding="utf-8")


def test_capacity_workflow_publishes_only_sanitized_aggregate_evidence() -> None:
    workflow = Path(".github/workflows/capacity-certification.yml").read_text(
        encoding="utf-8"
    )
    runner = Path("deploy/scripts/run-capacity-certification.sh").read_text(
        encoding="utf-8"
    )

    assert "capacity-certification.json" in workflow
    assert "capacity-certification.md" in workflow
    for private_name in (
        "viewer-manifest.json",
        "observer.ndjson",
        "k6.ndjson",
        "browser-private.log",
        "synthetic-capacity.ome.tiff",
    ):
        assert private_name not in workflow
    assert 'WORK_DIR="$(mktemp -d)"' in runner
    assert 'rm -rf -- "${WORK_DIR}"' in runner
    assert "LOAD_TEST_ADMIN_PASSWORD" not in runner.replace(
        ': "${LOAD_TEST_ADMIN_PASSWORD:?LOAD_TEST_ADMIN_PASSWORD is required}"', ""
    )


def test_runtime_container_inputs_are_pinned_by_digest() -> None:
    dockerfiles = (
        Path("deploy/Dockerfile.backend").read_text(encoding="utf-8"),
        Path("deploy/Dockerfile.web").read_text(encoding="utf-8"),
    )
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    for dockerfile in dockerfiles:
        for line in dockerfile.splitlines():
            if line.startswith("FROM "):
                parts = line.split()
                image = next(part for part in parts[1:] if not part.startswith("--"))
                assert "@sha256:" in image
                assert len(image.rsplit("@sha256:", 1)[1]) == 64
    tusd_line = next(
        line.strip() for line in compose.splitlines() if line.strip().startswith("image:")
    )
    assert "tusproject/tusd:v2.9.2@sha256:" in tusd_line
    assert len(tusd_line.rsplit("@sha256:", 1)[1]) == 64
    backend = dockerfiles[0]
    assert "pip install --no-cache-dir --require-hashes" in backend
    lockfile = Path("deploy/backend-requirements.txt").read_text(encoding="utf-8")
    assert "fastapi==0.139.2" in lockfile
    assert "pyvips==3.1.1" in lockfile
    assert "--hash=sha256:" in lockfile
    package = Path("package.json").read_text(encoding="utf-8")
    assert '"packageManager": "pnpm@11.9.0+sha512.' in package
    web = dockerfiles[1]
    assert web.startswith("FROM --platform=$BUILDPLATFORM node:")


def test_public_infrastructure_defaults_limit_operator_attack_surface() -> None:
    variables = Path("deploy/terraform/variables.tf").read_text(encoding="utf-8")
    duckdns = Path("deploy/scripts/duckdns.sh").read_text(encoding="utf-8")

    assert 'can(tonumber(split("/", var.admin_cidr)[1]) >= 24)' in variables
    assert "curl --fail --silent --show-error --max-time 15 --config -" in duckdns
    assert "token=${DUCKDNS_TOKEN}&" not in duckdns


def test_terraform_stays_within_the_approved_free_tier_footprint() -> None:
    terraform = Path("deploy/terraform/main.tf").read_text(encoding="utf-8")

    assert 'shape               = "VM.Standard.A1.Flex"' in terraform
    assert "ocpus         = 2" in terraform
    assert "memory_in_gbs = 12" in terraform
    assert "boot_volume_size_in_gbs = 50" in terraform
    assert "size_in_gbs         = 150" in terraform


def test_production_deploy_uses_temporary_oci_bastion_session() -> None:
    workflow = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8"
    )

    assert "secrets.OCI_CONFIG" in workflow
    assert "secrets.OCI_API_PRIVATE_KEY" in workflow
    assert "secrets.OCI_BASTION_KNOWN_HOSTS" in workflow
    assert "deploy/scripts/deploy-via-bastion.sh" in workflow
    assert "vars.PATHLAB_CLASSROOM_ENABLED" in workflow
    assert '"$GITHUB_SHA" "${PATHLAB_CLASSROOM_ENABLED}"' in workflow
    assert "secrets.OCI_DEPLOY_KEY" not in workflow
    assert "vars.OCI_HOST" not in workflow
    assert "pip install --require-hashes -r deploy/oci-cli-requirements.txt" in workflow
    lockfile = Path("deploy/oci-cli-requirements.txt").read_text(encoding="utf-8")
    assert "oci-cli==3.89.2" in lockfile
    assert "--hash=sha256:" in lockfile


def test_bastion_client_uses_ephemeral_key_and_always_deletes_session() -> None:
    script = Path("deploy/scripts/deploy-via-bastion.sh").read_text(
        encoding="utf-8"
    )

    assert "ssh-keygen" in script
    assert "oci bastion session create-managed-ssh" in script
    assert "oci bastion session list" in script
    assert "--wait-for-state" not in script
    assert "trap cleanup_bastion_session EXIT" in script
    assert "oci bastion session delete" in script
    assert "StrictHostKeyChecking=yes" in script
    assert "deploy ${TARGET_SHA}" in script
    assert '"${CLASSROOM_ENABLED}" =~ ^(true|false)$' in script
    assert 'classroom=${CLASSROOM_ENABLED}' in script


def test_load_observer_uses_ephemeral_bastion_and_an_exact_bounded_command() -> None:
    client = Path("deploy/scripts/observe-via-bastion.sh").read_text(encoding="utf-8")
    observer = Path("deploy/scripts/observe-load.sh").read_text(encoding="utf-8")
    release = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")

    assert "ssh-keygen" in client
    assert "trap cleanup_bastion_session EXIT" in client
    assert "oci bastion session delete" in client
    assert "StrictHostKeyChecking=yes" in client
    assert "observe-load ${DURATION}" in client
    assert "DURATION <= 900" in client
    assert "^observe-load[[:space:]]([0-9]{2,3})$" in release
    assert "exec \"${LIVE_DIR}/deploy/scripts/observe-load.sh\"" in release
    assert "/proc/stat" in observer
    assert "/proc/meminfo" in observer
    assert "docker inspect" in observer
    assert "releaseSha" in observer
    assert "/srv/pathlab/data" not in observer
    assert "docker compose logs" not in observer


def test_bastion_target_has_no_interactive_deployment_access() -> None:
    script = Path("deploy/scripts/configure-bastion-target.sh").read_text(
        encoding="utf-8"
    )

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
    assert "mv \"${LIVE_DIR}\" \"${ROLLBACK_DIR}\"" in script
    assert "mv \"${STAGE_DIR}\" \"${LIVE_DIR}\"" in script
    assert "curl --fail" in script
    assert "rollback_release" in script
    assert "flock" in script
    assert 'cat "${LIVE_DIR}/.pathlab-release"' in script
    assert 'git -C "${LIVE_DIR}" rev-parse HEAD' not in script
    assert "EXPECTED_SERVICES=$'api\\ncaddy\\ntile-service\\ntusd\\nworker'" in script


def test_release_script_preserves_environment_and_never_touches_data() -> None:
    script = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")

    assert 'install -m 600 "${LIVE_DIR}/deploy/.env"' in script
    assert "classroom=(true|false)" in script
    assert "PATHLAB_CLASSROOM_ENABLED=${CLASSROOM_ENABLED}" in script
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

    assert "workflow_dispatch:" in workflow
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


def test_security_workflow_supports_manual_event_recovery() -> None:
    workflow = Path(".github/workflows/security.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow


def test_web_container_includes_shared_viewer_ui_workspace() -> None:
    dockerfile = Path("deploy/Dockerfile.web").read_text(encoding="utf-8")

    assert "COPY apps/web ./apps/web" in dockerfile
    assert "COPY packages/viewer-ui ./packages/viewer-ui" in dockerfile
    assert dockerfile.index("COPY packages/viewer-ui") < dockerfile.index(
        "pnpm install --frozen-lockfile"
    )
