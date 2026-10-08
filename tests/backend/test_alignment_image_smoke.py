"""Smoke bootstrap and real supervisor resource rejection without engines."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_spawn_main_does_not_import_image_or_worker_runtime():
    script = ROOT / "scripts/alignment_image_smoke.py"
    program = """
import builtins, runpy, sys
original = builtins.__import__
def blocked(name, *args, **kwargs):
    if name.split('.')[0] in {'numpy', 'cv2', 'PIL', 'wsi_viewer'}:
        raise AssertionError('heavy spawn-main import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = blocked
runpy.run_path(sys.argv[1], run_name='__mp_main__')
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(script)],
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "PYTHONPATH": str(ROOT / "server")},
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(
    not sys.platform.startswith(("win", "linux")), reason="Windows/Linux process containment"
)
@pytest.mark.parametrize(
    "memory_bytes,timeout,reason", [(1, 8, "memory ceiling"), (512 * 1024**2, 1, "timeout")]
)
def test_stdlib_smoke_fixture_uses_real_supervisor_and_cleans_child(
    tmp_path, monkeypatch, memory_bytes, timeout, reason
):
    from wsi_viewer import worker
    from wsi_viewer.alignment import AlignmentRejected

    from scripts import alignment_image_smoke

    target = getattr(alignment_image_smoke, "resource_limit_fixture", None)
    assert callable(target), "The smoke requires an explicit stdlib-only resource fixture"
    context = worker.multiprocessing.get_context("spawn")
    children = []

    class RecordingContext:
        Event = context.Event
        Queue = context.Queue

        @staticmethod
        def Process(**kwargs):
            child = context.Process(**kwargs)
            children.append(child)
            return child

    monkeypatch.setattr(worker.multiprocessing, "get_context", lambda _: RecordingContext())
    unrelated = subprocess.Popen([sys._base_executable, "-c", "import time; time.sleep(120)"])
    try:
        with pytest.raises(AlignmentRejected, match=reason):
            worker._run_alignment_bounded(
                tmp_path,
                tmp_path,
                (10, 10),
                (10, 10),
                timeout_seconds=timeout,
                memory_bytes=memory_bytes,
                _child_target=target,
            )
        assert len(children) == 1
        assert not children[0].is_alive()
        assert children[0].exitcode is not None
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)
