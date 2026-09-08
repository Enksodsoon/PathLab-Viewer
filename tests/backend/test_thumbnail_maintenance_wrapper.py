import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name == "nt", reason="Linux deployment shell probe")
@pytest.mark.parametrize(
    "services,allowed",
    [("", True), ("postgres", True), ("api", False), ("postgres\nworker", False)],
)
def test_offline_wrapper_pins_image_and_rejects_live_services(tmp_path, services, allowed):
    root = tmp_path / "release"
    scripts = root / "deploy/scripts"
    scripts.mkdir(parents=True)
    wrapper = scripts / "repair-legacy-thumbnails.sh"
    shutil.copyfile("deploy/scripts/repair-legacy-thumbnails.sh", wrapper)
    sha = "a" * 40
    (root / ".pathlab-release").write_text(sha + "\n")
    calls = tmp_path / "calls"
    (scripts / "compose-pathlab.sh").write_text(
        "#!/bin/bash\nset -eu\n"
        'printf "%s %s\\n" "$PATHLAB_RELEASE_IMAGE_TAG" "$*" >> "$CAPTURE"\n'
        'if [[ "$1" == ps ]]; then printf "%s\\n" "$RUNNING"; fi\n'
    )
    result = subprocess.run(
        ["bash", str(wrapper)],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CAPTURE": str(calls),
            "RUNNING": services,
            "PATHLAB_RELEASE_IMAGE_TAG": "wrong-inherited-image",
        },
    )
    assert (result.returncode == 0) is allowed
    recorded = calls.read_text().splitlines()
    assert all(line.startswith(sha + " ") for line in recorded)
    assert (
        any("run --rm --no-deps --pull never api pathlab-admin" in line for line in recorded)
        is allowed
    )
    (root / ".pathlab-release").unlink()
    calls.unlink()
    assert subprocess.run(["bash", str(wrapper)], capture_output=True).returncode != 0
    assert not calls.exists()
