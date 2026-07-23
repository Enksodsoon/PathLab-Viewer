from pathlib import Path

from scripts import check_public_repository


def test_caddy_blocks_internal_api_routes_before_general_backend_proxy() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")

    internal = "@internal path /api/v1/internal/*"
    blocked = "respond @internal 404"
    backend = "handle @backend"
    assert internal in caddyfile
    assert blocked in caddyfile
    assert caddyfile.index(internal) < caddyfile.index(backend)
    assert caddyfile.index(blocked) < caddyfile.index(backend)


def test_caddy_sets_browser_security_policy() -> None:
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")

    assert "Content-Security-Policy" in caddyfile
    assert "default-src 'self'" in caddyfile
    assert "frame-ancestors 'none'" in caddyfile
    assert "Strict-Transport-Security" in caddyfile


def test_public_services_receive_only_the_storage_they_need() -> None:
    compose = Path("deploy/compose.yaml").read_text(encoding="utf-8")
    caddy = compose.split("\n  caddy:\n", maxsplit=1)[1].split(
        "\n  api:\n", maxsplit=1
    )[0]
    tusd = compose.split("\n  tusd:\n", maxsplit=1)[1].split(
        "\n  worker:\n", maxsplit=1
    )[0]
    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")

    assert "${PATHLAB_DATA_DIR:-/srv/pathlab/data}/public:/pathlab-public:ro" in caddy
    assert ":/pathlab-data:ro" not in caddy
    assert "${PATHLAB_DATA_DIR:-/srv/pathlab/data}/tus:/data/tus" in tusd
    assert "${PATHLAB_DATA_DIR:-/srv/pathlab/data}:/data" not in tusd
    assert "root * /pathlab-public" in caddyfile
    assert "root * /pathlab-data/public" not in caddyfile


def test_public_files_do_not_publish_the_production_endpoint() -> None:
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    release = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")
    dynamic_domain_suffix = "sslip" + ".io"
    retired_address_fragment = "140" + "-245-126-212"

    for content in (workflow, release):
        assert dynamic_domain_suffix not in content
        assert retired_address_fragment not in content
    assert "url: https://" not in workflow
    assert "Readiness: https://" not in workflow
    assert 'DOMAIN="$(awk' in release
    assert 'HEALTH_URL="https://${DOMAIN}/readyz"' in release


def test_duckdns_token_is_not_expanded_in_curl_process_arguments() -> None:
    script = Path("deploy/scripts/duckdns.sh").read_text(encoding="utf-8")

    assert "--config -" in script
    curl_command = script.split("curl", maxsplit=1)[1].splitlines()[0]
    assert "DUCKDNS_TOKEN" not in curl_command


def test_backups_are_owner_only_and_restore_validates_archive_paths() -> None:
    backup = Path("deploy/scripts/backup.sh").read_text(encoding="utf-8")
    restore = Path("deploy/scripts/restore.sh").read_text(encoding="utf-8")

    assert "umask 077" in backup
    assert "trap cleanup_temporary_backup EXIT" in backup
    assert "tar --list" in restore
    assert "Refusing unsafe archive entry" in restore
    assert "--no-same-owner" in restore
    assert "--no-same-permissions" in restore


def test_docker_context_excludes_private_data_and_credentials() -> None:
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    for pattern in (
        ".env",
        "data",
        "*.sqlite3",
        "*.pem",
        "*.key",
        "*.svs",
        "*.vsi",
        "*.tif",
        "*.tiff",
        "*.tar.gz",
    ):
        assert pattern in dockerignore
    assert "!.env.example" in dockerignore


def test_ci_runs_public_repository_and_history_guards() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "python scripts/check_public_repository.py" in workflow
    assert "gitleaks git --redact --no-banner" in workflow
    assert "PATHLAB_SECRET_KEY:" in workflow


def test_ci_scans_and_validates_built_images() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "pathlab-backend:ci" in workflow
    assert "pathlab-web:ci" in workflow
    assert "aquasecurity/trivy-action@" in workflow
    assert "caddy validate" in workflow
    assert "Weak deployment signing key was accepted" in workflow


def test_security_automation_is_configured() -> None:
    assert Path(".github/dependabot.yml").is_file()
    assert Path(".github/workflows/dependency-review.yml").is_file()
    assert Path(".github/workflows/codeql.yml").is_file()
    assert Path("scripts/check_public_repository.py").is_file()


def test_public_repository_guard_does_not_echo_sensitive_findings(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    secret = "ghp_" + ("A" * 24)
    (tmp_path / "sensitive.txt").write_text(secret, encoding="utf-8")
    monkeypatch.setattr(check_public_repository, "ROOT", tmp_path)
    monkeypatch.setattr(check_public_repository, "SELF", tmp_path / "guard.py")

    assert check_public_repository.main() == 1

    captured = capsys.readouterr()
    assert secret not in captured.err
    assert "sensitive.txt" not in captured.err
    assert "1 finding" in captured.err
