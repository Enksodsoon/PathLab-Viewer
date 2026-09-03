import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

SCANNER = Path(__file__).resolve().parents[2] / "scripts" / "check_public_repository.py"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )


def make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Safe User")
    git(repo, "config", "user.email", "12345+safe@users.noreply.github.com")
    (repo / "scripts").mkdir()
    shutil.copy2(SCANNER, repo / "scripts" / "check_public_repository.py")
    (repo / "README.md").write_text("clean\n", encoding="utf-8")
    (repo / "LICENSE").write_text(
        "Apache License\nVersion 2.0, January 2004\n", encoding="utf-8"
    )
    (repo / "NOTICE").write_text(
        "PathLab Viewer\nCopyright 2026 Example\nThird-party works retain their terms.\n",
        encoding="utf-8",
    )
    (repo / "CONTRIBUTING.md").write_text(
        "Signed-off-by: Name <safe@example.test>\n"
        "Developer Certificate of Origin\nDisclose tool-assisted material.\n",
        encoding="utf-8",
    )
    policy = repo / "docs" / "supply-chain" / "LICENSE_AND_NOTICE_POLICY.md"
    policy.parent.mkdir(parents=True)
    policy.write_text(
        "SPDX-License-Identifier: Apache-2.0\nSigned-off-by:\n"
        ".dist-info/licenses/\napps/web/dist\n",
        encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0.0.0"\n'
        'license = "Apache-2.0"\nlicense-files = ["LICENSE", "NOTICE"]\n',
        encoding="utf-8",
    )
    (repo / "package.json").write_text(
        '{"name":"fixture","private":true,"license":"Apache-2.0"}\n',
        encoding="utf-8",
    )
    web = repo / "apps" / "web"
    (web / "scripts").mkdir(parents=True)
    (web / "package.json").write_text(
        textwrap.dedent(
            """\
            {
              "name": "fixture-web",
              "private": true,
              "license": "Apache-2.0",
              "scripts": {"build": "node scripts/copy-release-legal-files.mjs"}
            }
            """
        ),
        encoding="utf-8",
    )
    (web / "scripts" / "copy-release-legal-files.mjs").write_text(
        "// SPDX-License-Identifier: Apache-2.0\n", encoding="utf-8"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    return repo, git(repo, "rev-parse", "HEAD").stdout.strip()


def run_scan(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/check_public_repository.py", *args],
        cwd=repo,
        text=True,
        capture_output=True,
    )


def test_current_tree_rejects_missing_root_notice(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    (repo / "NOTICE").unlink()
    git(repo, "add", "-u")

    scanned = run_scan(repo)

    assert scanned.returncode == 1
    assert "NOTICE:1: required license or notice file is missing" in scanned.stderr


def test_current_tree_rejects_package_license_mismatch(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    (repo / "apps" / "web" / "package.json").write_text(
        '{"name":"fixture-web","private":true,"license":"UNLICENSED",'
        '"scripts":{"build":"node scripts/copy-release-legal-files.mjs"}}\n',
        encoding="utf-8",
    )

    scanned = run_scan(repo)

    assert scanned.returncode == 1
    assert "JavaScript package license is not Apache-2.0" in scanned.stderr


def test_history_scan_catches_sensitive_file_deleted_before_final_tree(
    tmp_path: Path,
) -> None:
    repo, base = make_repo(tmp_path)
    (repo / "notes.txt").write_text(
        "private=" + "C:" + "\\\\Users\\\\alice\\\\case.txt\n",
        encoding="utf-8",
    )
    git(repo, "add", "notes.txt")
    git(repo, "commit", "-m", "temporary note")
    (repo / "notes.txt").unlink()
    git(repo, "add", "-u")
    git(repo, "commit", "-m", "remove note")

    assert run_scan(repo).returncode == 0
    scanned = run_scan(repo, "--history-base", base)
    assert scanned.returncode == 1
    assert "local workstation path" in scanned.stderr


def test_history_scan_catches_personal_commit_email(tmp_path: Path) -> None:
    repo, base = make_repo(tmp_path)
    git(repo, "config", "user.email", "person@" + "university.ac.th")
    (repo / "clean.txt").write_text("safe\n", encoding="utf-8")
    git(repo, "add", "clean.txt")
    git(repo, "commit", "-m", "new work")

    scanned = run_scan(repo, "--history-base", base)
    assert scanned.returncode == 1
    assert "commit author email" in scanned.stderr


def test_current_tree_catches_local_workstation_path(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    (repo / "notes.txt").write_text(
        "private=" + "/Users/" + "alice/project/data.txt\n",
        encoding="utf-8",
    )
    git(repo, "add", "notes.txt")
    scanned = run_scan(repo)
    assert scanned.returncode == 1
    assert "local workstation path" in scanned.stderr


def test_current_tree_allows_reserved_example_subdomain(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    (repo / "fixture.txt").write_text(
        "ssh-user=test@bastion.example\n",
        encoding="utf-8",
    )
    git(repo, "add", "fixture.txt")

    assert run_scan(repo).returncode == 0


def test_current_tree_rejects_example_lookalike_domain(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    (repo / "fixture.txt").write_text(
        "ssh-user=test@bastion.example." + "invalid-domain.com\n",
        encoding="utf-8",
    )
    git(repo, "add", "fixture.txt")

    scanned = run_scan(repo)
    assert scanned.returncode == 1
    assert "non-example email address" in scanned.stderr


def test_current_tree_allows_dicom_object_identifiers(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    (repo / "dicom.md").write_text(
        "SOP Class UID: 1.2.840.10008.5.1.4.1.1.77.1.6\n",
        encoding="utf-8",
    )
    git(repo, "add", "dicom.md")

    assert run_scan(repo).returncode == 0


def test_current_tree_still_rejects_standalone_public_ip(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    address = ".".join(("8", "8", "8", "8"))
    (repo / "host.txt").write_text(f"endpoint={address}:53\n", encoding="utf-8")
    git(repo, "add", "host.txt")

    scanned = run_scan(repo)
    assert scanned.returncode == 1
    assert "public IP address" in scanned.stderr


def test_current_tree_scans_private_key_and_service_extensions(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    (repo / "identity.pem").write_text(
        "-----BEGIN " + "PRIVATE KEY-----\nnot-a-real-key\n",
        encoding="utf-8",
    )
    (repo / "worker.service").write_text(
        "Environment=TOKEN=" + "ghp_" + "A" * 36 + "\n",
        encoding="utf-8",
    )
    git(repo, "add", "identity.pem", "worker.service")

    scanned = run_scan(repo)

    assert scanned.returncode == 1
    assert "identity.pem:1: private key material" in scanned.stderr
    assert "worker.service:1: credential-like token" in scanned.stderr


def test_current_tree_fails_closed_on_non_utf8_governed_text(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    (repo / "secrets.conf").write_bytes(b"name=\xff\xfe\n")
    git(repo, "add", "secrets.conf")

    scanned = run_scan(repo)

    assert scanned.returncode == 1
    assert "unreadable or non-UTF-8 governed text" in scanned.stderr


def test_history_fails_closed_on_non_utf8_governed_text(tmp_path: Path) -> None:
    repo, base = make_repo(tmp_path)
    (repo / "deleted.key").write_bytes(b"key=\xff\xfe\n")
    git(repo, "add", "deleted.key")
    git(repo, "commit", "-m", "temporary binary-looking key")
    (repo / "deleted.key").unlink()
    git(repo, "add", "-u")
    git(repo, "commit", "-m", "remove temporary key")

    scanned = run_scan(repo, "--history-base", base)

    assert scanned.returncode == 1
    assert "unreadable or non-UTF-8 governed text" in scanned.stderr


def test_history_scans_sensitive_service_extension_after_deletion(tmp_path: Path) -> None:
    repo, base = make_repo(tmp_path)
    (repo / "temporary.service").write_text(
        "Environment=TOKEN=" + "ghp_" + "B" * 36 + "\n",
        encoding="utf-8",
    )
    git(repo, "add", "temporary.service")
    git(repo, "commit", "-m", "temporary service")
    (repo / "temporary.service").unlink()
    git(repo, "add", "-u")
    git(repo, "commit", "-m", "remove temporary service")

    scanned = run_scan(repo, "--history-base", base)

    assert scanned.returncode == 1
    assert "credential-like token" in scanned.stderr


def test_current_tree_rejects_public_ipv6_and_unc_paths(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    ipv6 = ":".join(("2606", "4700", "4700", "")) + ":1111"
    unc = "\\\\" + "private-host" + "\\share\\case.txt"
    (repo / "network.conf").write_text(
        f"resolver=[{ipv6}]\nsource={unc}\n",
        encoding="utf-8",
    )
    git(repo, "add", "network.conf")

    scanned = run_scan(repo)

    assert scanned.returncode == 1
    assert "public IPv6 address" in scanned.stderr
    assert "local workstation path" in scanned.stderr


def test_lockfile_rejects_network_ip_but_allows_numeric_version(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    address = ".".join(("8", "8", "4", "4"))
    (repo / "pnpm-lock.yaml").write_text(
        "version: " + ".".join(("1", "2", "3", "4")) + "\n"
        f"resolution: https://{address}/pkg.tgz\n",
        encoding="utf-8",
    )
    git(repo, "add", "pnpm-lock.yaml")

    scanned = run_scan(repo)

    assert scanned.returncode == 1
    assert "public IP address" in scanned.stderr


def test_history_scan_allows_privacy_safe_commit_metadata(tmp_path: Path) -> None:
    repo, base = make_repo(tmp_path)
    (repo / "clean.txt").write_text("safe\n", encoding="utf-8")
    git(repo, "add", "clean.txt")
    git(repo, "commit", "-m", "new work")

    scanned = run_scan(repo, "--history-base", base)
    assert scanned.returncode == 0


def test_history_scan_allows_dependabot_noreply_commit_metadata(tmp_path: Path) -> None:
    repo, base = make_repo(tmp_path)
    git(repo, "config", "user.name", "dependabot[bot]")
    git(
        repo,
        "config",
        "user.email",
        "49699333+dependabot[bot]@users.noreply.github.com",
    )
    (repo / "clean.txt").write_text("safe\n", encoding="utf-8")
    git(repo, "add", "clean.txt")
    git(repo, "commit", "-m", "dependabot update")

    scanned = run_scan(repo, "--history-base", base)
    assert scanned.returncode == 0
