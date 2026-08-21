from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from deploy.scripts import capacity_fixtures

KEY = "e" * 64
SHA = "a" * 40
RUN = "123456"


def plan(path: Path) -> dict[str, Any]:
    unsigned = {
        "runId": RUN,
        "workflowSha": SHA,
        "windowEndEpochMs": (int(time.time()) + 3600) * 1000,
        "stages": [{"name": "smoke-2"}, {"name": "sustained-1200"}],
    }
    value = {
        **unsigned,
        "planDigest": hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


class FakeClient:
    instances: list[FakeClient] = []

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.calls: list[tuple[str, str, str | None]] = []
        self.__class__.instances.append(self)

    def login(self, username: str, password: str) -> None:
        assert username == "synthetic-admin"
        assert password == "synthetic-password"

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        synthetic_run: str | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        self.calls.append((method, path, synthetic_run))
        if path == "/api/v1/admin/classroom/sessions" and method == "GET":
            return {"sessions": []}
        if path == "/api/v1/admin/classroom/sessions" and method == "POST":
            return {
                "id": "11111111-1111-4111-8111-111111111111",
                "joinCode": "SYNTHETIC1",
                "syntheticRunId": RUN,
                "slides": [{
                    "id": "slide-1", "tileSource": "/tiles/public/v1/slide.dzi",
                    "width": 2048, "height": 1024, "tileSize": 512, "format": "jpg",
                }],
            }
        if path.startswith("/api/v1/admin/classroom/sessions/") and method == "GET":
            return {"session": {"syntheticRunId": RUN}}
        return b"fixture"


def create_args(tmp_path: Path) -> argparse.Namespace:
    plan_path = tmp_path / "plan.json"
    plan(plan_path)
    return argparse.Namespace(
        plan=plan_path,
        run_id=RUN,
        workflow_sha=SHA,
        base_url="https://viewer.example",
        username="synthetic-admin",
        password="synthetic-password",
        slide_id="slide-1",
        public_id="public-1",
        evidence_key=KEY,
        output=tmp_path / "fixtures.fernet",
    )


def test_fixture_bundle_is_encrypted_run_bound_and_materializes_private_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeClient.instances.clear()
    monkeypatch.setattr(capacity_fixtures, "Client", FakeClient)
    args = create_args(tmp_path)
    capacity_fixtures.create(args)

    encrypted = args.output.read_bytes()
    assert b"SYNTHETIC1" not in encrypted
    output = tmp_path / "materialized"
    capacity_fixtures.materialize(argparse.Namespace(
        input=args.output, evidence_key=KEY, run_id=RUN, workflow_sha=SHA, output_dir=output
    ))
    stages = json.loads((output / "stage-manifest.json").read_text())
    assert set(stages) == {"smoke-2", "sustained-1200"}
    assert len({entry["safetyNonce"] for entry in stages.values()}) == 2
    if os.name != "nt":
        assert not (args.output.stat().st_mode & 0o077)
    with pytest.raises(capacity_fixtures.FixtureError, match="stale or cross-run"):
        capacity_fixtures.decrypt_bundle(args.output, KEY, "another-run", SHA)


def test_fixture_create_reconciles_exact_session_after_partial_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingClient(FakeClient):
        def request(self, path: str, **kwargs: Any) -> Any:
            if path.endswith("slide.dzi"):
                raise capacity_fixtures.FixtureError("descriptor unavailable")
            return super().request(path, **kwargs)

    FailingClient.instances.clear()
    monkeypatch.setattr(capacity_fixtures, "Client", FailingClient)
    with pytest.raises(capacity_fixtures.FixtureError, match="descriptor unavailable"):
        capacity_fixtures.create(create_args(tmp_path))
    assert (
        "DELETE",
        "/api/v1/admin/classroom/sessions/11111111-1111-4111-8111-111111111111",
        RUN,
    ) in FailingClient.instances[0].calls


def test_fixture_create_rejects_cross_release_plan_before_login(tmp_path: Path) -> None:
    args = create_args(tmp_path)
    args.workflow_sha = "b" * 40

    with pytest.raises(capacity_fixtures.FixtureError, match="release does not match"):
        capacity_fixtures.create(args)


def test_fixture_create_refuses_an_active_classroom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ActiveClassroom(FakeClient):
        def request(self, path: str, **kwargs: Any) -> Any:
            if path == "/api/v1/admin/classroom/sessions":
                return {"sessions": [{"id": "real-session"}]}
            return super().request(path, **kwargs)

    monkeypatch.setattr(capacity_fixtures, "Client", ActiveClassroom)
    with pytest.raises(capacity_fixtures.FixtureError, match="Classroom is active"):
        capacity_fixtures.create(create_args(tmp_path))


def test_fixture_cleanup_refuses_unknown_session_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capacity_fixtures, "Client", FakeClient)
    args = create_args(tmp_path)
    capacity_fixtures.create(args)

    class UnknownOwner(FakeClient):
        def request(self, path: str, **kwargs: Any) -> Any:
            if kwargs.get("method", "GET") == "GET":
                return {"session": {"syntheticRunId": "real-classroom"}}
            return super().request(path, **kwargs)

    monkeypatch.setattr(capacity_fixtures, "Client", UnknownOwner)
    with pytest.raises(capacity_fixtures.FixtureError, match="refusing to remove"):
        capacity_fixtures.cleanup(argparse.Namespace(
            input=args.output, evidence_key=KEY, run_id=RUN, workflow_sha=SHA,
            base_url="https://viewer.example", username="synthetic-admin",
            password="synthetic-password",
        ))


def test_fixture_cleanup_is_idempotent_after_exact_session_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capacity_fixtures, "Client", FakeClient)
    args = create_args(tmp_path)
    capacity_fixtures.create(args)

    class MissingFixture(FakeClient):
        def request(self, path: str, **kwargs: Any) -> Any:
            if kwargs.get("method", "GET") == "GET":
                assert kwargs.get("expected") == (200, 404)
                return {"detail": {"code": "CLASSROOM_NOT_FOUND"}}
            return super().request(path, **kwargs)

    MissingFixture.instances.clear()
    monkeypatch.setattr(capacity_fixtures, "Client", MissingFixture)
    capacity_fixtures.cleanup(argparse.Namespace(
        input=args.output, evidence_key=KEY, run_id=RUN, workflow_sha=SHA,
        base_url="https://viewer.example", username="synthetic-admin",
        password="synthetic-password",
    ))
    assert all(call[0] != "DELETE" for call in MissingFixture.instances[0].calls)
