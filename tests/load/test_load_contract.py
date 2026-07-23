import os
import shutil
import subprocess
from pathlib import Path

import pytest

GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(GIT_BASH) if GIT_BASH.is_file() else shutil.which("bash")


def test_k6_script_uses_manifest_profiles_and_seventy_thirty_mix() -> None:
    script = Path("tests/load/viewer.js").read_text(encoding="utf-8")

    assert "validateManifest" in script
    assert "MANIFEST_PATH" in script
    assert "PROFILE" in script
    assert "vus: 100" in script
    assert "duration: '10m'" in script
    assert "vus: 2" in script
    assert "duration: '30s'" in script
    assert "COMMON_REQUESTS = 7" in script
    assert "RANDOM_REQUESTS = 3" in script
    assert "__VU" in script
    assert "tileFailures" in script
    assert "tileLatency" in script


def test_load_wrapper_requires_inputs_and_never_discovers_slide_ids() -> None:
    script = Path("deploy/scripts/run-viewer-load-test.sh").read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert "BASE_URL:?BASE_URL is required" in script
    assert "MANIFEST_PATH:?MANIFEST_PATH is required" in script
    assert '[[ "${MANIFEST_PATH}" = /* ]]' in script
    assert "command -v k6" in script
    assert "smoke|acceptance" in script
    assert "public_id" not in script.lower()
    assert "curl" not in script


@pytest.mark.skipif(BASH is None, reason="bash is unavailable")
def test_load_wrapper_rejects_missing_inputs() -> None:
    environment = os.environ.copy()
    environment.pop("BASE_URL", None)
    environment.pop("MANIFEST_PATH", None)

    result = subprocess.run(
        [str(BASH), "deploy/scripts/run-viewer-load-test.sh", "smoke"],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode != 0
    assert "BASE_URL is required" in result.stderr
