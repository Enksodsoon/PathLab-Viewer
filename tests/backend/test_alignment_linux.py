"""Actual Linux owned-session cleanup; Windows cannot establish runtime proof."""

import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

import pytest
from wsi_viewer import worker
from wsi_viewer.alignment import AlignmentRejected

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux PID-fd containment"
)


def _resistant_child(
    reference,
    moving,
    ref_size,
    mov_size,
    engine,
    settings,
    artifact,
    output,
    seed=None,
    startup_gate=None,
):
    os.setsid()
    if startup_gate is not None and not startup_gate.wait(20):
        return
    directory = Path(reference)
    grandchild = (
        "import os,signal,time; from pathlib import Path; "
        "os.setpgid(0,0); signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"Path({str(directory / 'grand-ready')!r}).touch(); time.sleep(120)"
    )
    child = (
        "import os,json,signal,subprocess,sys,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"p=subprocess.Popen([sys.executable,'-c',{grandchild!r}]); "
        f"Path({str(directory / 'tree.json')!r}).write_text(json.dumps([os.getpid(),p.pid])); "
        "time.sleep(120)"
    )
    subprocess.Popen([sys.executable, "-c", child])
    deadline = time.monotonic() + 10
    while not (directory / "handles-ready").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("test descendant handles were not captured")
        time.sleep(0.02)
    if settings["mode"] == "normal":
        output.put({"ok": True, "result": {"status": "approximate"}})
    elif settings["mode"] == "root-exit":
        os._exit(0)
    else:
        time.sleep(120)


@pytest.mark.parametrize("mode", ["normal", "root-exit", "timeout", "cancel"])
def test_term_resistant_descendants_end_even_after_root_exit(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(worker, "_alignment_child", _resistant_child)
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    descriptors = []
    try:

        def heartbeat():
            if (tmp_path / "grand-ready").exists() and not descriptors:
                for pid in json.loads((tmp_path / "tree.json").read_text()):
                    descriptors.append(os.pidfd_open(pid))
                (tmp_path / "handles-ready").touch()
            if mode == "cancel" and descriptors:
                raise AlignmentRejected("test cancellation")

        if mode == "normal":
            worker._run_alignment_bounded(
                tmp_path,
                tmp_path,
                (10, 10),
                (10, 10),
                engine_settings={"mode": mode},
                timeout_seconds=8,
                memory_bytes=2 * 1024**3,
                heartbeat=heartbeat,
            )
        else:
            with pytest.raises(AlignmentRejected):
                worker._run_alignment_bounded(
                    tmp_path,
                    tmp_path,
                    (10, 10),
                    (10, 10),
                    engine_settings={"mode": mode},
                    timeout_seconds=8,
                    memory_bytes=2 * 1024**3,
                    heartbeat=heartbeat,
                )
        import select

        assert len(descriptors) == 2
        for descriptor in descriptors:
            poll = select.poll()
            poll.register(descriptor, select.POLLIN)
            assert poll.poll(1000), "TERM-resistant descendant survived"
        assert unrelated.poll() is None
    finally:
        for descriptor in descriptors:
            with suppress(ProcessLookupError):
                signal.pidfd_send_signal(descriptor, signal.SIGKILL)
            os.close(descriptor)
        unrelated.terminate()
        unrelated.wait(timeout=5)
