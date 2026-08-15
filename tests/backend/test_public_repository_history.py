import shutil
import subprocess
import sys
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