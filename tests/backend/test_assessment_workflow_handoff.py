import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Exercises the Ubuntu Actions shell")
WORKFLOW = Path(".github/workflows/assessment-capacity.yml")
ORIGIN = "https://protected-qualification.example.test"
TILE_PATH = "/assessment-assets/public/grant/version/slide_files/15/1_2.jpg"


def job_script(job: str, marker: str) -> str:
    source = WORKFLOW.read_text().split(f"  {job}:\n", 1)[1]
    source = source.split(marker, 1)[1].split("        run: |\n", 1)[1]
    lines = []
    for line in source.splitlines():
        if line and not line.startswith("          "):
            break
        lines.append(line)
    return re.sub(r"\$\{\{.*?\}\}", "synthetic", textwrap.dedent("\n".join(lines)))


@pytest.mark.parametrize("foreign", [False, True])
def test_output_transfers_only_same_origin_path_without_the_protected_secret(tmp_path, foreign):
    source = WORKFLOW.read_text()
    script = source.split('          [[ "$tile_url"', 1)[1]
    script = '[[ "$tile_url"' + script.split('          echo "start_epoch=', 1)[0]
    output = tmp_path / "outputs"
    result = subprocess.run(
        ["bash", "-eu", "-c", script],
        env={
            **os.environ,
            "CAPACITY_BASE_URL": ORIGIN,
            "tile_url": ("https://foreign.test" if foreign else ORIGIN) + TILE_PATH,
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    if foreign:
        assert result.returncode != 0
        assert not output.exists()
    else:
        assert result.returncode == 0, result.stderr
        assert output.read_text() == f"tile_path={TILE_PATH}\n"
        assert ORIGIN not in output.read_text()
    assert "outputs.tile_url" not in source


@pytest.mark.parametrize("job", ["observer", "shard"])
@pytest.mark.parametrize("tile_path", [TILE_PATH, "", "/unrelated/path"])
def test_consumers_rebuild_tile_url_and_reject_missing_handoff(tmp_path, job, tile_path):
    marker = "Poll readiness" if job == "observer" else "Execute exactly one"
    script = job_script(job, marker)
    executable = tmp_path / ("python" if job == "observer" else "k6")
    executable.write_text('#!/bin/bash\nprintf "%s\\n" "${TILE_URL:-}" "$@" > "$MEASURED"\n')
    executable.chmod(0o755)
    measured = tmp_path / "measured"
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "BASE_URL": ORIGIN,
        "CAPACITY_BASE_URL": ORIGIN,
        "TILE_PATH": tile_path,
        "PUBLIC_ID": "public",
        "ACCESS_CODE": "test-only",
        "START_EPOCH": "1",
        "RELEASE_SHA": "a" * 40,
        "HOST_OBSERVER_URL": ORIGIN + "/sample",
        "MEASURED": str(measured),
    }
    result = subprocess.run(
        ["bash", "-eu", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if tile_path != TILE_PATH:
        assert result.returncode != 0
        assert not measured.exists()
    else:
        assert result.returncode == 0, result.stderr
        arguments = measured.read_text().splitlines()
        if job == "observer":
            assert arguments[arguments.index("--tile-url") + 1] == ORIGIN + TILE_PATH
            assert "--output" in arguments
        else:
            assert arguments[0] == ORIGIN + TILE_PATH
