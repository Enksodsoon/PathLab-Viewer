from pathlib import Path


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


def test_public_files_do_not_publish_the_production_endpoint() -> None:
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    release = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")

    for content in (workflow, release):
        assert "sslip.io" not in content
        assert "140-245-126-212" not in content
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


def test_ci_runs_public_repository_guard() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "python scripts/check_public_repository.py" in workflow
    assert "PATHLAB_SECRET_KEY:" in workflow


def test_security_automation_is_configured() -> None:
    assert Path(".github/dependabot.yml").is_file()
    assert Path(".github/workflows/dependency-review.yml").is_file()
    assert Path(".github/workflows/codeql.yml").is_file()
    assert Path("scripts/check_public_repository.py").is_file()
