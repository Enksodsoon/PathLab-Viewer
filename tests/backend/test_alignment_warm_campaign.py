"""Full planned denominators and resume identity without engine execution."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def controller(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/benchmark_alignment_warm_process.py"
    spec = importlib.util.spec_from_file_location("alignment_warm_campaign", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "validate_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_private_output", lambda *args: None)
    monkeypatch.setattr(module, "_runtime_versions", lambda: {"loaded-cv2": "frozen"})

    def pair_digest(pair, recipe, settings, **kwargs):
        return hashlib.sha256(
            json.dumps([pair, recipe, settings, kwargs], sort_keys=True).encode()
        ).hexdigest()

    monkeypatch.setattr(module, "pair_digest", pair_digest)
    return module


def _manifest():
    return {
        "pairs": [
            {
                "reference": {"path": f"r{n}", "size": [100, 100], "sha": "a" * 64},
                "moving": {"path": f"m{n}", "size": [100, 100], "sha": "b" * 64},
                "kind": "positive" if n < 12 else "negative",
                "inputDigests": ["a" * 64, "b" * 64],
            }
            for n in range(16)
        ]
    }


def test_full_144_denominator_retained_and_resume_executes_no_calls(
    controller, tmp_path, monkeypatch
):
    calls = []

    def trial(*args, **kwargs):
        calls.append(kwargs)
        return {
            "terminalContainmentVerified": True,
            "invocations": [
                {
                    "invocationOrdinal": 1,
                    "invocationExecuted": True,
                    "result": {"ok": True, "result": {"status": "approximate"}},
                },
                {
                    "invocationOrdinal": 2,
                    "invocationExecuted": None,
                    "result": {"ok": False, "type": "MissingInvocationReceipt"},
                },
            ],
        }

    monkeypatch.setattr(controller, "run_warm_bounded", trial)
    report = controller.campaign(
        _manifest(), tmp_path, frozen_manifest_sha="c" * 64, source_head="d" * 40
    )
    assert len(calls) == 144
    assert report["plannedInvocations"] == 288
    assert len(report["rows"]) == 144
    assert sum(len(row["invocations"]) for row in report["rows"]) == 288
    assert all(row["invocations"][1]["outcome"] == "failed-or-missing" for row in report["rows"])
    assert report["qualified"] is False
    controller.campaign(_manifest(), tmp_path, frozen_manifest_sha="c" * 64, source_head="d" * 40)
    assert len(calls) == 144


def test_changed_runtime_invalidates_previous_receipts(controller, tmp_path, monkeypatch):
    calls = []

    def trial(*args, **kwargs):
        calls.append(True)
        return {"terminalContainmentVerified": True, "invocations": []}

    monkeypatch.setattr(controller, "run_warm_bounded", trial)
    controller.campaign(_manifest(), tmp_path, frozen_manifest_sha="c" * 64, source_head="d" * 40)
    monkeypatch.setattr(controller, "_runtime_versions", lambda: {"loaded-cv2": "changed"})
    controller.campaign(_manifest(), tmp_path, frozen_manifest_sha="c" * 64, source_head="d" * 40)
    assert len(calls) == 288
    assert len(list((tmp_path / "cache").glob("*.json"))) == 288


def test_exhausted_admission_records_two_failures_without_supervisor_call(
    controller, tmp_path, monkeypatch
):
    clock = iter(
        value for n in range(144) for value in (n * 1000, n * 1000 + 0.5, n * 1000 + 600.5)
    )
    monkeypatch.setattr(controller.time, "monotonic", lambda: next(clock))

    def forbidden(*args, **kwargs):
        pytest.fail("exhausted admission must not invoke the child supervisor")

    monkeypatch.setattr(controller, "run_warm_bounded", forbidden)
    report = controller.campaign(
        _manifest(), tmp_path, frozen_manifest_sha="c" * 64, source_head="d" * 40
    )
    assert len(report["rows"]) == 144
    assert sum(len(row["invocations"]) for row in report["rows"]) == 288
    assert all(
        invocation["invocationExecuted"] is False
        and invocation["failureType"] == "AdmissionBudgetExhausted"
        for row in report["rows"]
        for invocation in row["invocations"]
    )


def test_fractional_admission_grant_rounds_down_without_extending_deadline(
    controller, tmp_path, monkeypatch
):
    clock = iter(value for n in range(144) for value in (n * 1000, n * 1000 + 0.25, n * 1000 + 0.5))
    monkeypatch.setattr(controller.time, "monotonic", lambda: next(clock))
    calls = []

    def trial(*args, **kwargs):
        calls.append(kwargs)
        return {"terminalContainmentVerified": True, "invocations": []}

    monkeypatch.setattr(controller, "run_warm_bounded", trial)
    controller.campaign(_manifest(), tmp_path, frozen_manifest_sha="c" * 64, source_head="d" * 40)
    assert len(calls) == 144
    assert all(call["timeout_seconds"] == 599 for call in calls)
    assert [call["absolute_deadline"] for call in calls] == [n * 1000 + 600 for n in range(144)]
    assert all(call["settings"]["timeoutSeconds"] == 600 for call in calls)
