from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def launch(tmp_path: Path, configuration: str) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    if os.name == "nt":
        candidate = Path("C:/Program Files/Git/bin/bash.exe")
        bash = str(candidate) if candidate.exists() else bash
    if not bash:
        pytest.skip("Bash is required to exercise the production Compose launcher")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "compose-pathlab.sh"
    script.write_text(Path("deploy/scripts/compose-pathlab.sh").read_text(), newline="\n")
    (tmp_path / ".env").write_text(configuration, newline="\n")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$@"\n'
        'printf "capability=%s\\nprofiles=%s\\n" "$PATHLAB_ASSESSMENT_ENABLED" '
        '"${COMPOSE_PROFILES:-}" >&2\n',
        newline="\n",
    )
    docker.chmod(0o755)
    environment = dict(os.environ)
    environment.pop("PATHLAB_COMPOSE_ENV_FILE", None)
    return subprocess.run(
        [
            bash,
            "-c",
            'cd "$1"; export PATH="$PWD/bin:$PATH"; exec bash scripts/compose-pathlab.sh up -d',
            "compose-test",
            tmp_path.as_posix(),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        timeout=15,
    )


def test_enabled_studio_launches_dedicated_service_with_postgres(tmp_path: Path) -> None:
    result = launch(
        tmp_path,
        "PATHLAB_DATABASE_ENGINE=postgres\nPATHLAB_ASSESSMENT_ENABLED=true\n"
        "PATHLAB_IDENTITY_GOVERNANCE_ENABLED=true\n",
    )
    assert result.returncode == 0, result.stderr
    arguments = result.stdout.splitlines()
    assert arguments[arguments.index("--profile") + 1] == "assessment"
    assert any(value.endswith("compose.postgres.yaml") for value in arguments)
    assert any(value.endswith("compose.assessment.yaml") for value in arguments)
    assert arguments[-2:] == ["up", "-d"]


@pytest.mark.parametrize("configuration", ["", "PATHLAB_ASSESSMENT_ENABLED=false\n"])
def test_ordinary_release_keeps_studio_profile_absent(tmp_path: Path, configuration: str) -> None:
    result = launch(tmp_path, configuration)
    assert result.returncode == 0, result.stderr
    assert "--profile" not in result.stdout.splitlines()
    assert "compose.assessment.yaml" not in result.stdout


def test_shell_overrides_cannot_advertise_studio_without_its_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATHLAB_ASSESSMENT_ENABLED", "true")
    monkeypatch.setenv("COMPOSE_PROFILES", "assessment")
    result = launch(tmp_path, "PATHLAB_ASSESSMENT_ENABLED=false\n")
    assert result.returncode == 0
    assert "--profile" not in result.stdout.splitlines()
    assert result.stderr == "capability=false\nprofiles=\n"


@pytest.mark.parametrize(
    "configuration",
    [
        "PATHLAB_ASSESSMENT_ENABLED=true\nPATHLAB_IDENTITY_GOVERNANCE_ENABLED=true\n",
        "PATHLAB_DATABASE_ENGINE=postgres\nPATHLAB_ASSESSMENT_ENABLED=true\n",
        "PATHLAB_ASSESSMENT_ENABLED=TRUE\n",
    ],
)
def test_unsafe_studio_configuration_fails_before_docker(
    tmp_path: Path, configuration: str
) -> None:
    result = launch(tmp_path, configuration)
    assert result.returncode == 2
    assert not result.stdout
