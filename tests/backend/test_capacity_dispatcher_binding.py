from __future__ import annotations

import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from deploy.scripts.capacity_dispatcher_binding import BindingError, validate_binding_metadata

CONTROLLER = "/run/pathlab-capacity-exact-run-controller\n"


@dataclass(frozen=True)
class Facts:
    st_mode: int
    st_uid: int = 0


def regular(mode: int, *, uid: int = 0) -> Facts:
    return Facts(stat.S_IFREG | mode, uid)


def directory(mode: int, *, uid: int = 0) -> Facts:
    return Facts(stat.S_IFDIR | mode, uid)


def test_trusted_readable_controller_does_not_require_an_executable_bit() -> None:
    result = validate_binding_metadata(
        CONTROLLER,
        pointer=regular(0o600),
        directory=directory(0o700),
        script=regular(0o400),
    )

    assert result == Path("/run/pathlab-capacity-exact-run-controller/capacity-control-host.sh")


@pytest.mark.parametrize(
    ("pointer", "directory_facts", "script", "message"),
    [
        (regular(0o620), directory(0o700), regular(0o755), "pointer permissions"),
        (regular(0o600), directory(0o720), regular(0o755), "directory permissions"),
        (regular(0o600), directory(0o700), regular(0o775), "owner-readable"),
        (regular(0o600), directory(0o700), regular(0o200), "owner-readable"),
        (regular(0o600, uid=1), directory(0o700), regular(0o755), "pointer is not"),
        (regular(0o600), directory(0o700, uid=1), regular(0o755), "directory is not"),
        (regular(0o600), directory(0o700), regular(0o755, uid=1), "script is not"),
        (
            Facts(stat.S_IFLNK | 0o777),
            directory(0o700),
            regular(0o755),
            "pointer is not",
        ),
        (
            regular(0o600),
            Facts(stat.S_IFLNK | 0o777),
            regular(0o755),
            "directory is not",
        ),
        (
            regular(0o600),
            directory(0o700),
            Facts(stat.S_IFLNK | 0o777),
            "script is not",
        ),
    ],
)
def test_untrusted_metadata_is_rejected(
    pointer: Facts, directory_facts: Facts, script: Facts, message: str
) -> None:
    with pytest.raises(BindingError, match=message):
        validate_binding_metadata(
            CONTROLLER,
            pointer=pointer,
            directory=directory_facts,
            script=script,
        )


@pytest.mark.parametrize(
    "value",
    [
        "/tmp/pathlab-capacity-exact-run-controller\n",
        "/run/pathlab-capacity-EXACT-controller\n",
        "/run/pathlab-capacity-a-controller/../other\n",
        "/run/pathlab-capacity-a-controller\ntrailing\n",
        "/run/pathlab-capacity-a-controller",
    ],
)
def test_controller_path_must_match_the_exact_run_binding(value: str) -> None:
    with pytest.raises(BindingError, match="invalid"):
        validate_binding_metadata(
            value,
            pointer=regular(0o600),
            directory=directory(0o700),
            script=regular(0o755),
        )


def test_dispatcher_uses_validated_readable_script_without_executable_test() -> None:
    dispatcher = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")
    capacity_branch = dispatcher[
        dispatcher.index('if [[ "${REQUEST}" == capacity-arm') : dispatcher.index(
            'if [[ "${REQUEST}" == capacity-recover'
        )
    ]

    assert "capacity_dispatcher_binding.py" in capacity_branch
    assert "${CONTROLLER_DIR}/capacity_dispatcher_binding.py" in capacity_branch
    assert "${LIVE_DIR}/deploy/scripts/capacity_dispatcher_binding.py" not in capacity_branch
    assert "-x" not in capacity_branch
    assert 'exec bash "${CONTROLLER_SCRIPT}"' in capacity_branch
    assert "^/run/pathlab-capacity-[a-z0-9-]{1,64}-controller$" in capacity_branch
    assert "-L /run/pathlab-capacity-controller" in capacity_branch
    assert "0:600" in capacity_branch
    assert "0:700" in capacity_branch
    assert capacity_branch.count("0:755") >= 1


def test_dispatch_selection_and_execution_hold_the_common_shared_lock() -> None:
    dispatcher = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")
    capacity_branch = dispatcher[
        dispatcher.index('if [[ "${REQUEST}" == capacity-arm') : dispatcher.index(
            'if [[ "${REQUEST}" == capacity-recover'
        )
    ]

    arm_bypass = capacity_branch.index('if [[ "${REQUEST}" == capacity-arm\\ * ]]')
    shared_lock = capacity_branch.index("flock --shared --timeout 10")
    pointer_read = capacity_branch.index("IFS= read -r CONTROLLER_DIR")
    frozen_exec = capacity_branch.index('exec bash "${CONTROLLER_SCRIPT}"')
    fallback_exec = capacity_branch.rindex(
        'exec bash "${LIVE_DIR}/deploy/scripts/capacity-control-host.sh"'
    )
    assert arm_bypass < shared_lock < pointer_read < frozen_exec < fallback_exec
    assert "PATHLAB_CAPACITY_DISPATCH_LOCK_FD=8" in capacity_branch
    assert "capacity-recover" not in capacity_branch


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("flock") is None,
    reason="requires Linux flock",
)
def test_dispatch_lock_survives_exec_and_same_description_can_upgrade(tmp_path: Path) -> None:
    lock = tmp_path / "controller.lock"
    holder = subprocess.Popen(
        [
            "bash",
            "-c",
            'exec 8<>"$1"; flock --shared 8; printf "ready\\n"; exec bash -c \'read -r _\'',
            "dispatcher-lock-holder",
            str(lock),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdout.readline() == "ready\n"

    blocked = subprocess.run(
        ["flock", "--exclusive", "--nonblock", str(lock), "true"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode != 0

    assert holder.stdin is not None
    holder.stdin.write("release\n")
    holder.stdin.flush()
    assert holder.wait(timeout=5) == 0
    admitted = subprocess.run(
        ["flock", "--exclusive", "--nonblock", str(lock), "true"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert admitted.returncode == 0

    upgraded = subprocess.run(
        [
            "bash",
            "-c",
            "exec 8<>\"$1\"; flock --shared 8; exec bash -c 'flock --exclusive --nonblock 8'",
            "dispatcher-lock-upgrade",
            str(lock),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgraded.returncode == 0, upgraded.stderr
