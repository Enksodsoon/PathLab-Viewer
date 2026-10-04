"""Exercise the actual stdlib Linux session supervisor without WSI dependencies."""

from __future__ import annotations

import ast
import json
import multiprocessing
import os
import select
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from wsi_viewer.alignment_processes import LinuxAlignmentGroup  # noqa: E402


def _optional_rss_reader():
    # Extract unchanged optional telemetry without importing any WSI libraries.
    # This is a helper-level baseline contrast, not an actual worker runtime.
    source = Path(__file__).resolve().parents[1] / "server/wsi_viewer/worker.py"
    node = next(
        node for node in ast.parse(source.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name == "_process_rss_bytes"
    )
    namespace = {"Path": Path, "sys": sys, "os": os}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["_process_rss_bytes"]


def _target(directory: str, mode: str, gate: object) -> None:
    os.setsid()
    if not gate.wait(20):
        return
    grandchild = (
        "import os,signal,time; from pathlib import Path; "
        "os.setpgid(0,0); signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"Path({directory!r}+'/grand-ready').touch(); time.sleep(120)"
    )
    child = (
        "import os,json,signal,subprocess,sys,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"p=subprocess.Popen([sys.executable,'-c',{grandchild!r}]); "
        f"Path({directory!r}+'/tree.json').write_text(json.dumps([os.getpid(),p.pid])); "
        "time.sleep(120)"
    )
    subprocess.Popen([sys.executable, "-c", child])
    while not Path(directory, "handles-ready").exists():
        time.sleep(0.01)
    if mode == "root-exit":
        os._exit(0)
    if mode == "normal":
        return
    time.sleep(120)


def main() -> None:
    if not sys.platform.startswith("linux"):
        raise SystemExit("Linux runtime required; this host cannot establish Linux proof")
    receipts = []
    optional_rss = _optional_rss_reader()
    context = multiprocessing.get_context("spawn")
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        for mode in (
            "normal", "root-exit", "timeout", "cancel",
            "rss-live-unreadable", "rss-after-loss", "rss-exit-race",
        ):
            with tempfile.TemporaryDirectory(prefix="alignment-containment-") as directory:
                path = Path(directory)
                gate = context.Event()
                target_mode = {"rss-after-loss": "normal", "rss-exit-race": "root-exit"}.get(
                    mode, mode
                )
                process = context.Process(target=_target, args=(directory, target_mode, gate))
                group = None
                descriptors = []
                try:
                    process.start()
                    group = LinuxAlignmentGroup(process.pid, 10)
                    gate.set()
                    deadline = time.monotonic() + 10
                    while not (path / "grand-ready").exists():
                        if time.monotonic() >= deadline:
                            raise RuntimeError("contained tree did not start")
                        time.sleep(0.01)
                    descendants = json.loads((path / "tree.json").read_text())
                    for pid in descendants:
                        descriptors.append(os.pidfd_open(pid))
                    assert os.getpgid(descendants[1]) != process.pid
                    assert os.getsid(descendants[1]) == process.pid
                    assert set(descendants).issubset(group.members())
                    (path / "handles-ready").touch()
                    rss_proof = {}
                    if mode == "rss-live-unreadable":
                        member = descendants[0]
                        before = group.members()[member]
                        real_read = Path.read_text

                        def read(value, *args, _member=member, _read=real_read, **kwargs):
                            if value == Path(f"/proc/{_member}/statm"):
                                raise PermissionError("injected live RSS loss")
                            return _read(value, *args, **kwargs)

                        with patch.object(Path, "read_text", read):
                            assert optional_rss(member) == 0
                            try:
                                group.resident_bytes()
                            except OSError as error:
                                assert "RSS unavailable" in str(error)
                            else:
                                raise AssertionError("live unreadable RSS was silently omitted")
                            assert group.members()[member] == before
                        rss_proof = {
                            "sameOwnedLiveIdentity": True,
                            "optionalTelemetryReturnsZero": True,
                            "enforcementRejected": True,
                        }
                    if target_mode in {"normal", "root-exit"}:
                        process.join(5)
                        assert not process.is_alive()
                    if mode == "rss-exit-race":
                        # A real root exited after the earlier membership snapshot.
                        captured = {**group.members(), process.pid: group.start_time}
                        with patch.object(group, "members", return_value=captured):
                            assert group.resident_bytes() > 0
                        assert optional_rss(process.pid) == 0
                        rss_proof = {"confirmedExitIsBenign": True}
                    if mode == "rss-after-loss":
                        assert group.resident_bytes() > 0
                        rss_proof = {"secondAdmissionAfterProvedCleanup": True}
                    elif mode == "timeout":
                        time.sleep(0.2)
                    group.close()
                    process.join(5)
                    assert not process.is_alive()
                    for descriptor in descriptors:
                        poller = select.poll()
                        poller.register(descriptor, select.POLLIN)
                        assert poller.poll(1000), "contained descendant survived"
                    assert not group.members()
                    assert unrelated.poll() is None
                    receipts.append(
                        {
                            "mode": mode,
                            "descendantsTerminal": 2,
                            "termResistantNewProcessGroup": True,
                            "unrelatedProcessUnaffected": True,
                            **rss_proof,
                        }
                    )
                finally:
                    if group is not None:
                        group.close()
                    for descriptor in descriptors:
                        with suppress(ProcessLookupError):
                            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                        os.close(descriptor)
                    if process.is_alive():
                        process.terminate()
                    process.join(5)
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)
    print(
        json.dumps(
            {
                "schema": "pathlab-linux-containment-smoke/1",
                "cases": receipts,
                "scope": (
                    "owned-session; descendants creating a new session require cgroup containment"
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
