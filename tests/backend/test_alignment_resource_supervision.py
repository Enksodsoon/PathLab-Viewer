"""Lightweight spawned children test error classification and resource receipts."""

import os
import sys

import pytest
from wsi_viewer import worker
from wsi_viewer.alignment import AlignmentRejected
from wsi_viewer.alignment_resources import EngineResourceUnavailable


def _resource_result_child(
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
    if sys.platform.startswith("linux"):
        os.setsid()
    if startup_gate is not None and not startup_gate.wait(20):
        return
    if settings["mode"] == "unavailable":
        output.put(
            {
                "ok": False,
                "type": "EngineResourceUnavailable",
                "error": "declared local resource unavailable",
            }
        )
    elif settings["mode"] == "rejected":
        output.put({"ok": False, "type": "AlignmentRejected", "error": "unsupported anatomy"})
    else:
        output.put({"ok": True, "result": {"status": "approximate"}})


@pytest.mark.parametrize("mode", ["unavailable", "rejected", "success"])
def test_supervisor_preserves_resource_unavailable_type_and_measured_scope(
    tmp_path, monkeypatch, mode
):
    monkeypatch.setattr(worker, "_alignment_child", _resource_result_child)
    options = dict(engine_settings={"mode": mode}, timeout_seconds=10, memory_bytes=2 * 1024**3)
    if mode == "success":
        receipt = worker._run_alignment_bounded(tmp_path, tmp_path, (10, 10), (10, 10), **options)
    else:
        expected = EngineResourceUnavailable if mode == "unavailable" else AlignmentRejected
        with pytest.raises(expected) as error:
            worker._run_alignment_bounded(tmp_path, tmp_path, (10, 10), (10, 10), **options)
        assert type(error.value) is expected
        receipt = error.value.resource_metrics
    assert receipt["peakMemoryBytes"] > 0
    if sys.platform.startswith("linux"):
        assert receipt["processContainment"] == "linux-owned-session"
        assert receipt["memoryMeasurementScope"] == "linux-owned-session-sampled-rss"
        assert "peakCommittedMemoryBytes" not in receipt
