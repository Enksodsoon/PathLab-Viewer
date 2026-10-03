"""A disconnected deployment must recover with its output pipe already closed."""

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
BASH = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")


@pytest.mark.skipif(not BASH, reason="bash unavailable")
@pytest.mark.parametrize("swapped", [False, True])
def test_closed_ssh_output_recovers_stopped_services(tmp_path, swapped):
    source = ROOT / "deploy/scripts/deploy-release.sh"
    trace = tmp_path / "recovery"
    live = tmp_path / "live"
    (live / "deploy").mkdir(parents=True)

    def quote(path):
        return shlex.quote(str(path).replace("\\", "/"))

    signal_trap = next(
        line
        for line in source.read_text().splitlines()
        if line.startswith("trap interrupt_deployment ")
    )
    script = tmp_path / "disconnect.sh"
    script.write_text(
        f"""export PATHLAB_DEPLOY_RELEASE_LIBRARY_ONLY=1
source {quote(source)}
LIVE_DIR={quote(live)}
OLD_SERVICES_STOPPED=1
SWAPPED={int(swapped)}
compose_release() {{ printf 'compose output\\n'; printf 'restart\\n' >> {quote(trace)}; }}
rollback_release() {{
 printf 'rollback output\\n'; printf 'rollback\\n' >> {quote(trace)}; exit 1
}}
trap cleanup_exit EXIT
{signal_trap}
read -r ready
printf 'write to disconnected SSH\\n'
exit 0
""",
        newline="\n",
    )
    process = subprocess.Popen([BASH, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    assert process.stdout is not None and process.stdin is not None
    process.stdout.close()
    process.stdin.write(b"ready\n")
    process.stdin.close()
    assert process.wait(timeout=10) != 0
    assert trace.read_text().splitlines() == (["rollback"] if swapped else ["restart"])
