import importlib.util
import io
import json
import sys
import time
from email.message import Message
from pathlib import Path

import pytest


@pytest.mark.parametrize("payload,content_type,accepted", [
    (b"\xff\xd8\xffjpeg", "image/jpeg", True),
    (b"<Image/>", "application/xml", False),
    (b"<html/>", "text/html", False),
    (b"not an image", "image/jpeg", False),
])
def test_tile_observer_rejects_metadata_and_html(monkeypatch, payload, content_type, accepted):
    module = _observer()
    response = io.BytesIO(payload)
    response.status = 200
    response.headers = Message()
    response.headers["Content-Type"] = content_type
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: response)
    if accepted:
        assert module.fetch("https://app.example.test/tile.jpeg", {}, jpeg=True)[0] == payload
    else:
        with pytest.raises(RuntimeError, match="JPEG"):
            module.fetch("https://app.example.test/tile.jpeg", {}, jpeg=True)


def _observer():
    path = Path(__file__).parents[2] / "scripts" / "assessment_capacity_observer.py"
    spec = importlib.util.spec_from_file_location("assessment_observer", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample():
    return {
        "releaseSha": "a" * 40,
        "databaseEngine": "postgresql",
        "sampledAt": int(time.time()),
        "pressureRoles": ["api", "assessment", "classroom"],
        "workerGenerations": {
            "api": ["a" * 32], "assessment": ["b" * 32, "c" * 32], "classroom": ["d" * 32]
        },
        "databaseMaxConnections": 32,
        "databaseConnections": 20,
        "poolTimeouts": 0,
        "lockTimeouts": 0,
        "assessmentWorkers": 2,
        "restarts": 0,
        "oomKills": 0,
        "cpuPercent": 50.5,
        "memoryPercent": 65,
        "swapBytes": 0,
    }


def test_observer_accepts_complete_telemetry():
    _observer().validate_host_sample(_sample(), "a" * 40)


@pytest.mark.parametrize("field", list(_sample()))
def test_observer_rejects_missing_telemetry(field):
    sample = _sample()
    del sample[field]
    with pytest.raises(ValueError):
        _observer().validate_host_sample(sample, "a" * 40)


@pytest.mark.parametrize("value", [None, False, "0", -1, float("nan"), float("inf")])
def test_observer_rejects_invalid_counter(value):
    sample = {**_sample(), "poolTimeouts": value}
    with pytest.raises(ValueError):
        _observer().validate_host_sample(sample, "a" * 40)


def test_observer_rejects_release_change_during_campaign():
    with pytest.raises(ValueError):
        _observer().validate_host_sample(_sample(), "b" * 40)


def test_observer_rejects_stale_or_single_worker_samples():
    for sample in (
        {**_sample(), "sampledAt": int(time.time()) - 60},
        {**_sample(), "workerGenerations": {"assessment": ["a" * 32]}},
    ):
        with pytest.raises(ValueError):
            _observer().validate_host_sample(sample, "a" * 40)


def test_observer_keeps_credentials_scoped_to_their_target(monkeypatch, tmp_path):
    module = _observer()
    output = tmp_path / "observer.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "observer",
            "--base-url",
            "https://app.example.test",
            "--host-observer-url",
            "https://host.example.test/observe",
            "--administration-id",
            "synthetic",
            "--tile-url",
            "https://app.example.test/tile",
            "--release-sha",
            "a" * 40,
            "--start-epoch",
            "100",
            "--duration-seconds",
            "1",
            "--output",
            str(output),
        ],
    )
    monkeypatch.setenv("ASSESSMENT_ADMIN_COOKIE", "synthetic-cookie")
    monkeypatch.setenv("ASSESSMENT_ADMIN_CSRF", "synthetic-csrf")
    monkeypatch.setenv("ASSESSMENT_OBSERVER_TOKEN", "synthetic-observer")
    clock = iter([0, 0, 2])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(module.time, "time", lambda: 100)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    seen = []

    def fetch_json(url, headers):
        seen.append((url, headers))
        return (_sample() if "host.example" in url else {"status": "ready"}), 1

    def fetch_tile(url, headers, *, jpeg):
        assert jpeg is True
        seen.append((url, headers))
        return b"synthetic", 1

    monkeypatch.setattr(module, "fetch_json", fetch_json)
    monkeypatch.setattr(module, "fetch", fetch_tile)
    assert module.main() == 0
    for url, headers in seen:
        if "host.example" in url:
            assert headers == {"Authorization": "Bearer synthetic-observer"}
        else:
            assert headers == {"Cookie": "synthetic-cookie", "X-CSRF-Token": "synthetic-csrf"}
    assert json.loads(output.read_text(encoding="utf-8"))["releaseSha"] == "a" * 40
