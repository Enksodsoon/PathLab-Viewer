"""Finite operational profiling fixtures; no service or engine execution."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def module():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "operational_profile", root / "scripts/measure_alignment_operational_profile.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "database.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE jobs(id TEXT,status TEXT,checkpoint TEXT,created_at TEXT,"
            "updated_at TEXT,failure_code TEXT,resource_limits TEXT,kind TEXT)"
        )
    return path


def test_queue_interval_not_exact_zero_when_first_poll_is_terminal(module):
    assert module.queue_interval("2026-10-04T00:00:00", None, "2026-10-04T00:00:00.750+00:00") == [
        0,
        0.75,
    ]
    assert module.queue_interval(
        "2026-10-04T00:00:00", "2026-10-04T00:00:00.25Z", "2026-10-04T00:00:00.750Z"
    ) == [0.25, 0.75]


def test_all_api_refusals_retain_nine_rows_null_application_and_resume(module, database, tmp_path):
    class Api:
        base = "http://127.0.0.1:12345"
        calls = []

        def request(self, path, body=None):
            self.calls.append(body)
            return 409, {"category": "api-request-rejected"}

    api = Api()
    report = module.profile(api, database, "s", 1, tmp_path / "output", {"proof": 1})
    assert len(report["rows"]) == 9 and len(api.calls) == 9
    assert all(
        row["outcome"] == "api-rejected"
        and row["candidate"] is None
        and row["queueSeconds"] is None
        and row["browserApplicationSeconds"] is None
        and row["humanCorrectionEffort"] is None
        for row in report["rows"]
    )
    module.profile(api, database, "s", 1, tmp_path / "output", {"proof": 1})
    assert len(api.calls) == 9
    with pytest.raises(ValueError, match="binding differs"):
        module.profile(api, database, "s", 1, tmp_path / "output", {"proof": 2})


def test_ack_lost_preserves_partial_and_never_requeues(module, database, tmp_path):
    class Api:
        base = "http://127.0.0.1:12345"
        calls = 0

        def request(self, path, body=None):
            self.calls += 1
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)",
                    (
                        "job",
                        "queued",
                        json.dumps({"comparisonSetId": "s", "engine": body["engines"][0]}),
                        "2026-10-04T00:00:00",
                        "2026-10-04T00:00:00",
                        None,
                        "{}",
                        "align_benchmark",
                    ),
                )
            raise TimeoutError("acknowledgement lost")

    api = Api()
    with pytest.raises(TimeoutError):
        module.profile(api, database, "s", 1, tmp_path / "output", {"proof": 1})
    assert module.jobs(database, "s", module.RECIPES[0])[0]["status"] == "queued"
    receipt = json.loads((tmp_path / "output/private" / f"{module.RECIPES[0]}.json").read_bytes())
    assert receipt["completed"] is False
    with pytest.raises(ValueError, match="reconciliation"):
        module.profile(api, database, "s", 1, tmp_path / "output", {"proof": 1})
    assert api.calls == 1


def test_exact_one_job_required_even_if_api_ack_claims_one(module, database, tmp_path):
    class Api:
        base = "http://127.0.0.1:12345"
        calls = 0

        def request(self, path, body=None):
            self.calls += 1
            with sqlite3.connect(database) as connection:
                for ordinal in range(2):
                    connection.execute(
                        "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)",
                        (
                            str(ordinal),
                            "queued",
                            json.dumps({"comparisonSetId": "s", "engine": body["engines"][0]}),
                            "2026-10-04T00:00:00",
                            "2026-10-04T00:00:00",
                            None,
                            "{}",
                            "align_benchmark",
                        ),
                    )
            return 202, {"queuedCandidates": 1}

    api = Api()
    with pytest.raises(RuntimeError, match="exactly one"):
        module.profile(api, database, "s", 1, tmp_path / "output", {"proof": 1})
    assert api.calls == 1


def test_nonterminal_observation_deadline_halts_before_next_recipe(
    module, database, tmp_path, monkeypatch
):
    clock = iter([0, 0, 0, 661])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))

    class Api:
        base = "http://127.0.0.1:12345"
        calls = 0

        def request(self, path, body=None):
            self.calls += 1
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)",
                    (
                        "job",
                        "checkpointing",
                        json.dumps({"comparisonSetId": "s", "engine": body["engines"][0]}),
                        "2026-10-04T00:00:00",
                        "2026-10-04T00:00:00",
                        "ALIGNMENT_CONTAINMENT_LOST",
                        "{}",
                        "align_benchmark",
                    ),
                )
            return 202, {"queuedCandidates": 1}

    api = Api()
    with pytest.raises(RuntimeError, match="no next job"):
        module.profile(api, database, "s", 1, tmp_path / "output", {"proof": 1})
    assert api.calls == 1


def test_original_service_port_cannot_be_admitted(module, database, tmp_path):
    guard = {
        "disposableRoot": str(tmp_path),
        "database": str(database),
        "schema": module.POLICY,
        "ownedDisposable": True,
        "comparisonSetId": "s",
        "baseUrl": "http://127.0.0.1:8001",
        "sourceProofSha256": "a" * 64,
        "configurationProofSha256": "b" * 64,
        "serviceOwnershipProofSha256": "c" * 64,
        "qualificationScope": "operational-only-no-anatomical-qualification",
    }
    with pytest.raises(ValueError, match="disposable"):
        module.validate_guard(guard, guard["baseUrl"], database, "s")
    guard["baseUrl"] = "http://127.0.0.1:12345"
    module.validate_guard(guard, guard["baseUrl"], database, "s")


def test_running_then_requeued_preserves_initial_queue_interval(
    module, database, tmp_path, monkeypatch
):
    original_jobs = module.jobs
    phase = {}
    timestamps = iter(f"2026-10-04T00:{n // 60:02d}:{n % 60:02d}+00:00" for n in range(100))
    monkeypatch.setattr(module, "_utc", lambda: next(timestamps))
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    def observed_jobs(db, set_id, recipe):
        rows = original_jobs(db, set_id, recipe)
        if rows:
            count = phase.get(recipe, 0)
            phase[recipe] = count + 1
            status = ("queued", "queued", "running", "queued", "succeeded")[min(count, 4)]
            with sqlite3.connect(db) as connection:
                connection.execute("UPDATE jobs SET status=? WHERE id=?", (status, recipe))
            rows = original_jobs(db, set_id, recipe)
        return rows

    class Api:
        base = "http://127.0.0.1:12345"
        recipe = None

        def request(self, path, body=None):
            if body is not None:
                self.recipe = body["engines"][0]
                with sqlite3.connect(database) as connection:
                    connection.execute(
                        "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)",
                        (
                            self.recipe,
                            "queued",
                            json.dumps({"comparisonSetId": "s", "engine": self.recipe}),
                            "2026-10-04T00:00:00",
                            "2026-10-04T00:00:00",
                            None,
                            json.dumps(
                                {"timeoutSeconds": 600, "memoryBytes": 7 * 1024**3, "cpuThreads": 2}
                            ),
                            "align_benchmark",
                        ),
                    )
                return 202, {"queuedCandidates": 1}
            return 200, {
                "candidates": [
                    {
                        "engine": self.recipe,
                        "setVersion": 1,
                        "id": self.recipe,
                        "currentPair": True,
                        "registration": {"status": "approximate"},
                    }
                ]
            }

    monkeypatch.setattr(module, "jobs", observed_jobs)
    report = module.profile(Api(), database, "s", 1, tmp_path / "output", {"proof": 1})
    assert len(report["rows"]) == 9
    first = report["rows"][0]
    assert first["queueObservationIntervalSeconds"] == [3, 4]
    assert first["lastQueuedObservationAt"] == "2026-10-04T00:00:03+00:00"
    assert first["firstNonqueuedObservationAt"] == "2026-10-04T00:00:04+00:00"
    assert first["candidateDigest"] == module._digest(first["candidate"])
    assert first["job"]["resource_limits"]["cpuThreads"] == 2
    assert first["queueSeconds"] is None
    assert report["qualified"] is False


def test_owned_loopback_api_ignores_inherited_proxy_configuration(module, monkeypatch):
    consulted = []

    def inherited_proxy():
        consulted.append(True)
        return {"http": "http://unowned.invalid:3128"}

    monkeypatch.setattr(module.urllib.request, "getproxies", inherited_proxy)
    api = module.Api("http://127.0.0.1:12345", {"Cookie": "disposable-fixture"})
    assert consulted == []
    assert all(
        not isinstance(handler, module.urllib.request.ProxyHandler) or not handler.proxies
        for handler in api.opener.handlers
    )


def test_server_error_is_uncertain_even_when_job_not_yet_visible(module, database, tmp_path):
    class Api:
        base = "http://127.0.0.1:12345"
        calls = 0

        def request(self, path, body=None):
            self.calls += 1
            return 503, {"category": "api-request-rejected"}

    api = Api()
    with pytest.raises(RuntimeError, match="stop for reconciliation"):
        module.profile(api, database, "s", 1, tmp_path / "output", {"proof": 1})
    assert api.calls == 1
    receipt = json.loads(
        (tmp_path / "output" / "private" / f"{module.RECIPES[0]}.json").read_bytes()
    )
    assert receipt["completed"] is False
    assert receipt["outcome"] == "api-acknowledgement-uncertain"
