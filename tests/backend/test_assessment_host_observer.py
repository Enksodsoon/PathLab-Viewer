import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "assessment_host_observer", "deploy/scripts/assessment_host_observer.py"
)
assert SPEC is not None and SPEC.loader is not None
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)


def test_pressure_requires_every_distinct_worker_and_real_counters() -> None:
    first = {"counterGeneration": "a" * 32, "poolTimeouts": 1, "lockTimeouts": 2}
    second = {"counterGeneration": "b" * 32, "poolTimeouts": 3, "lockTimeouts": 4}
    assert observer.pressure_sample([first, second], 2) == ({"a" * 32, "b" * 32}, 4, 6)
    for values in ([first], [first, first], [first, {**second, "poolTimeouts": None}]):
        with pytest.raises(ValueError):
            observer.pressure_sample(values, 2)


def test_memory_and_cpu_do_not_substitute_zero_for_missing_data() -> None:
    assert observer.cpu_ticks("cpu 10 20 30 40 50 60 70 80 100 200") == (360, 90)
    with pytest.raises(ValueError):
        observer.cpu_ticks("cpu 1 2")
    assert observer.memory_sample(
        "MemTotal: 100 kB\nMemAvailable: 25 kB\nSwapTotal: 10 kB\nSwapFree: 6 kB"
    ) == (75, 4096)
    with pytest.raises(KeyError):
        observer.memory_sample("MemTotal: 100 kB\nMemAvailable: 25 kB")


def test_endpoint_authentication_and_freshness_fail_closed() -> None:
    token = b"test-host-token-32-characters-long"
    auth = "Bearer " + token.decode()
    sample = {"sampledAt": 100, "poolTimeouts": 3}
    assert observer.sample_response("/sample", "", token, sample, 105)[0] == 404
    assert observer.sample_response("/other", auth, token, sample, 105)[0] == 404
    assert observer.sample_response("/sample", auth, token, sample, 105) == (200, sample)
    for stale in ({}, {"error": "missing"}, {"sampledAt": 1}, {"sampledAt": 110}):
        code, payload = observer.sample_response("/sample", auth, token, stale, 105)
        assert code == 503
        assert "poolTimeouts" not in payload


def test_collector_reports_measured_pressure_and_rejects_worker_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "1" * 40
    (tmp_path / ".pathlab-release").write_text(sha)
    ids = {role: f"{index:064x}" for index, role in enumerate(sorted(observer.ROLES), 1)}
    roles = {value: key for key, value in ids.items()}
    config = {
        "releaseSha": sha,
        "liveDir": str(tmp_path),
        "containers": ids,
        "databaseUser": "pathlab",
        "databaseName": "pathlab",
    }
    rotated = False

    def command(*args: str) -> str:
        if args[:2] == ("docker", "inspect"):
            return json.dumps(
                [
                    {
                        "Id": identity,
                        "RestartCount": 2 if role == "worker" else 0,
                        "Config": {"Image": f"pathlab-{role}:{sha}"},
                        "State": {
                            "Running": True,
                            "Paused": False,
                            "Restarting": False,
                            "Pid": int(identity, 16),
                        },
                    }
                    for role, identity in ids.items()
                ]
            )
        role = roles[args[2]]
        if args[3] == "psql":
            return json.dumps({"version": 180006, "maximum": 32, "current": 9})
        if args[3] == "cat":
            return "low 0\noom 1\noom_kill " + ("1" if role == "assessment" else "0")
        assert args[3] == "python"
        count = observer.PRESSURE_ROLES[role][1]
        return json.dumps(
            [
                {
                    "counterGeneration": f"{int(ids[role], 16) * 10 + index + int(rotated):032x}",
                    "serviceRole": "general" if role == "api" else role,
                    "poolTimeouts": 1,
                    "lockTimeouts": 2,
                }
                for index in range(count)
            ]
        )

    original = Path.read_text
    ticks = iter(
        [
            "cpu 10 0 10 80 0 0 0 0",
            "cpu 20 0 20 90 0 0 0 0",
            "cpu 30 0 30 100 0 0 0 0",
        ]
    )

    def read(path: Path, *args: object, **kwargs: object) -> str:
        if path.as_posix() == "/proc/stat":
            return next(ticks)
        if path.as_posix() == "/proc/meminfo":
            return "MemTotal: 100 kB\nMemAvailable: 25 kB\nSwapTotal: 10 kB\nSwapFree: 6 kB"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(observer, "run", command)
    monkeypatch.setattr(
        observer, "oom_kills", lambda pid, identity: int(identity == ids["assessment"])
    )
    monkeypatch.setattr(Path, "read_text", read)
    collector = observer.Collector(config)
    sample = collector.collect()
    assert sample["poolTimeouts"] == 4
    assert sample["lockTimeouts"] == 8
    assert sample["assessmentWorkers"] == 2
    assert sample["oomKills"] == 1
    assert sample["restarts"] == 2
    assert sample["databaseConnections"] == 9
    assert sample["cpuPercent"] == pytest.approx(200 / 3)
    rotated = True
    with pytest.raises(ValueError, match="generation changed"):
        collector.collect()
