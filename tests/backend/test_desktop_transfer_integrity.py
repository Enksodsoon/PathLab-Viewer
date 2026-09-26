import asyncio
import threading
from pathlib import Path

import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_api import _client, _desktop_authorization
from wsi_viewer.classroom_runtime import ClassroomSingletonLock
from wsi_viewer.database import session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import DesktopIngest, ResultDelivery, Slide


def reserve(client, authorization, kind):
    if kind == "results":
        with session_factory(client.app.state.settings)() as database:
            slide = Slide(
                display_name="Synthetic",
                original_filename="source.ome.tif",
                source_bytes=12,
                sha256="b" * 64,
                state=SlideState.READY_PRIVATE,
                slide_metadata={"width": 100, "height": 100},
            )
            database.add(slide)
            database.commit()
            slide_id = slide.id
        route = f"/api/v2/desktop/slides/{slide_id}/result-deliveries"
        payload = {
            "artifactRevisionId": "revision",
            "slideSha256": "b" * 64,
            "payloadLength": 12,
            "payloadSha256": "a" * 64,
            "schema": "pathlab-private-results/v1",
        }
    elif kind == "ome":
        route = "/api/v1/desktop/ome-ingests"
        payload = {
            "displayName": "Synthetic",
            "artifactRevisionId": "revision",
            "omeLength": 12,
            "omeSha256": "a" * 64,
            "profile": "ome-dynamic-v1",
            "width": 512,
            "height": 512,
            "downsample": 1.0,
            "jpegQuality": 75,
        }
    else:
        route = "/api/v1/desktop/ingests"
        payload = {
            "displayName": "Synthetic",
            "artifactRevisionId": "revision",
            "packageLength": 12,
            "packageSha256": "a" * 64,
            "manifestSha256": "b" * 64,
            "derivativeBytes": 12,
            "derivativeFileCount": 1,
        }
    return route, payload


def paths(client, kind, route, document):
    root = client.app.state.settings.data_root
    if kind == "results":
        return route + "/" + document["id"], root / "staging" / "results" / (
            document["id"] + ".plresults"
        )
    # Resolve using the production path helper; no guessed spool filename.
    from wsi_viewer.desktop_finalizer import desktop_upload_path
    from wsi_viewer.storage import StorageLayout

    with session_factory(client.app.state.settings)() as database:
        ingest = database.get(DesktopIngest, document["id"])
        target = desktop_upload_path(StorageLayout(root), ingest)
    return "/api/v2/desktop/ingests/" + document["id"], target


@pytest.mark.parametrize("kind", ["prepared", "ome", "results"])
def test_http_chunks_and_cancellation_cannot_overlap_same_spool(tmp_path: Path, kind: str):
    with _client(tmp_path) as client:
        authorization = _desktop_authorization(client)
        route, payload = reserve(client, authorization, kind)
        created = client.post(route, headers=authorization, json=payload)
        assert created.status_code == 201, created.text
        document = created.json()
        cancel_url, target = paths(client, kind, route, document)
        other_authorization = _desktop_authorization(client)

        async def scenario():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=client.app, raise_app_exceptions=False),
                base_url="http://testserver",
            ) as browser:
                entered, release = asyncio.Event(), asyncio.Event()

                async def first_body():
                    entered.set()
                    await release.wait()
                    yield b"AAAA"

                first = asyncio.create_task(
                    browser.patch(
                        document["uploadUrl"],
                        headers={**authorization, "Upload-Offset": "0"},
                        content=first_body(),
                    )
                )
                await asyncio.wait_for(entered.wait(), 3)
                try:
                    second = await browser.patch(
                        document["uploadUrl"],
                        headers={**authorization, "Upload-Offset": "0"},
                        content=b"BBBBBB",
                    )
                    assert second.status_code == 409
                    unauthenticated = await browser.patch(
                        document["uploadUrl"],
                        headers={"Upload-Offset": "0"},
                        content=b"X",
                    )
                    assert unauthenticated.status_code == 401
                    unowned = await browser.patch(
                        document["uploadUrl"],
                        headers={**other_authorization, "Upload-Offset": "0"},
                        content=b"X",
                    )
                    assert unowned.status_code == 404
                    cancelled = await browser.delete(cancel_url, headers=authorization)
                    assert cancelled.status_code == 409
                    assert target.exists()
                finally:
                    release.set()
                    accepted = await first
                assert accepted.status_code == 202
                assert accepted.json()["receivedBytes"] == 4
                assert target.read_bytes() == b"AAAA"
                stale = await browser.patch(
                    document["uploadUrl"],
                    headers={**authorization, "Upload-Offset": "0"},
                    content=b"BBBBBB",
                )
                assert stale.status_code == 409
                retried = await browser.patch(
                    document["uploadUrl"],
                    headers={**authorization, "Upload-Offset": "4"},
                    content=b"BBBBBB",
                )
                assert retried.status_code == 202
                assert retried.json()["receivedBytes"] == 10
                assert target.read_bytes() == b"AAAABBBBBB"
                assert (await browser.delete(cancel_url, headers=authorization)).status_code == 204
                assert not target.exists()

        asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["prepared", "ome", "results"])
def test_failed_spool_creation_does_not_strand_committed_transfer(
    tmp_path: Path, monkeypatch, kind: str
):
    with _client(tmp_path) as client:
        authorization = _desktop_authorization(client)
        route, payload = reserve(client, authorization, kind)
        original = Path.open

        def denied(path, mode="r", *args, **kwargs):
            if mode == "xb" or (mode == "wb" and path.suffix == ".plresults"):
                raise PermissionError("synthetic spool creation denied")
            return original(path, mode, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(Path, "open", denied)
            original_touch = Path.touch

            def denied_touch(path, *args, **kwargs):
                if path.suffix == ".plresults":
                    raise PermissionError("synthetic spool creation denied")
                return original_touch(path, *args, **kwargs)

            patch.setattr(Path, "touch", denied_touch)
            with pytest.raises(PermissionError, match="synthetic spool creation denied"):
                client.post(route, headers=authorization, json=payload)
        model = ResultDelivery if kind == "results" else DesktopIngest
        with session_factory(client.app.state.settings)() as database:
            assert database.scalar(select(model)) is None
        retry = client.post(route, headers=authorization, json=payload)
        assert retry.status_code == 201, retry.text
        _, target = paths(client, kind, route, retry.json())
        assert target.is_file()


@pytest.mark.parametrize("kind", ["prepared", "ome", "results"])
def test_creation_commit_failure_cleans_only_created_spool(tmp_path: Path, monkeypatch, kind: str):
    with _client(tmp_path) as client:
        authorization = _desktop_authorization(client)
        route, payload = reserve(client, authorization, kind)
        assert client.get("/api/v1/desktop/capabilities", headers=authorization).status_code == 200
        opened = []
        original = Path.open

        def capture(path, mode="r", *args, **kwargs):
            result = original(path, mode, *args, **kwargs)
            if mode == "xb":
                opened.append(path)
            return result

        def reject(_database):
            raise RuntimeError("synthetic creation commit failure")

        with monkeypatch.context() as patch:
            patch.setattr(Path, "open", capture)
            event.listen(Session, "before_commit", reject)
            try:
                with pytest.raises(RuntimeError, match="synthetic creation commit failure"):
                    client.post(route, headers=authorization, json=payload)
            finally:
                event.remove(Session, "before_commit", reject)
        assert len(opened) == 1
        assert not opened[0].exists()
        model = ResultDelivery if kind == "results" else DesktopIngest
        with session_factory(client.app.state.settings)() as database:
            assert database.scalar(select(model)) is None
        assert client.post(route, headers=authorization, json=payload).status_code == 201


@pytest.mark.parametrize("kind", ["prepared", "results"])
@pytest.mark.parametrize("failure", ["commit", "unlink"])
def test_cancel_preserves_source_until_durable_ack(
    tmp_path: Path, monkeypatch, caplog, kind: str, failure: str
):
    with _client(tmp_path) as client:
        authorization = _desktop_authorization(client)
        route, payload = reserve(client, authorization, kind)
        created = client.post(route, headers=authorization, json=payload).json()
        cancel_url, target = paths(client, kind, route, created)
        assert (
            client.patch(
                created["uploadUrl"],
                headers={**authorization, "Upload-Offset": "0"},
                content=b"AAAA",
            ).status_code
            == 202
        )

        def reject(_database):
            raise RuntimeError("synthetic cancel commit failure")

        original_unlink = Path.unlink

        def denied(path, *args, **kwargs):
            if path == target:
                raise PermissionError("synthetic cleanup denial")
            return original_unlink(path, *args, **kwargs)

        if failure == "commit":
            event.listen(Session, "before_commit", reject)
            try:
                with pytest.raises(RuntimeError, match="synthetic cancel commit failure"):
                    client.delete(cancel_url, headers=authorization)
            finally:
                event.remove(Session, "before_commit", reject)
            head = client.head(created["uploadUrl"], headers=authorization)
            assert head.status_code == 200
            assert head.headers["Upload-Offset"] == "4"
            assert (
                client.patch(
                    created["uploadUrl"],
                    headers={**authorization, "Upload-Offset": "4"},
                    content=b"BB",
                ).status_code
                == 202
            )
            assert target.read_bytes() == b"AAAABB"
        else:
            monkeypatch.setattr(Path, "unlink", denied)
            assert client.delete(cancel_url, headers=authorization).status_code == 204
            assert target.read_bytes() == b"AAAA"
            assert "DESKTOP_CANCEL_SPOOL_CLEANUP_FAILED" in caplog.text
            assert "source retained" in caplog.text
            model = ResultDelivery if kind == "results" else DesktopIngest
            with session_factory(client.app.state.settings)() as database:
                record = database.get(model, created["id"])
                assert record is None if kind == "results" else record.status == "cancelled"


@pytest.mark.parametrize("kind", ["prepared", "ome", "results"])
def test_creation_commit_acknowledgement_failure_keeps_durable_spool(tmp_path, monkeypatch, kind):
    with _client(tmp_path) as client:
        authorization = _desktop_authorization(client)
        route, payload = reserve(client, authorization, kind)
        assert client.get("/api/v1/desktop/capabilities", headers=authorization).status_code == 200
        original_commit = Session.commit

        def lost_ack(database):
            creating = any(
                isinstance(record, (DesktopIngest, ResultDelivery))
                for record in database.identity_map.values()
            )
            original_commit(database)
            if creating:
                raise RuntimeError("synthetic lost commit acknowledgement")

        with monkeypatch.context() as patch:
            patch.setattr(Session, "commit", lost_ack)
            response = client.post(route, headers=authorization, json=payload)
        assert response.status_code == 201, response.text
        _, target = paths(client, kind, route, response.json())
        assert target.is_file()
        assert client.patch(
            response.json()["uploadUrl"],
            headers={**authorization, "Upload-Offset": "0"}, content=b"AAAA",
        ).status_code == 202
        assert target.read_bytes() == b"AAAA"


@pytest.mark.parametrize("kind", ["prepared", "ome", "results"])
def test_stream_abort_releases_native_lock_for_retry(tmp_path: Path, kind: str):
    with _client(tmp_path) as client:
        authorization = _desktop_authorization(client)
        route, payload = reserve(client, authorization, kind)
        document = client.post(route, headers=authorization, json=payload).json()

        async def scenario():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=client.app, raise_app_exceptions=False),
                base_url="http://testserver",
            ) as browser:

                async def broken_body():
                    yield b"AAAA"
                    raise RuntimeError("synthetic stream abort")

                failed = await browser.patch(
                    document["uploadUrl"],
                    headers={**authorization, "Upload-Offset": "0"},
                    content=broken_body(),
                )
                assert failed.status_code == 500
                accepted = await browser.patch(
                    document["uploadUrl"],
                    headers={**authorization, "Upload-Offset": "0"},
                    content=b"BBBB",
                )
                assert accepted.status_code == 202
                assert accepted.json()["receivedBytes"] == 4
                assert (await browser.head(document["uploadUrl"], headers=authorization)).headers[
                    "Upload-Offset"
                ] == "4"

        asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["prepared", "results"])
def test_offset_is_reread_after_native_lock_acquisition(tmp_path: Path, monkeypatch, kind: str):
    with _client(tmp_path) as client:
        authorization = _desktop_authorization(client)
        route, payload = reserve(client, authorization, kind)
        document = client.post(route, headers=authorization, json=payload).json()
        paused, allow_lock = threading.Event(), threading.Event()
        original_acquire = ClassroomSingletonLock.acquire
        calls = []

        def acquire(transfer_lock):
            calls.append(transfer_lock.path)
            if len(calls) == 2:
                paused.set()
                assert allow_lock.wait(5)
            return original_acquire(transfer_lock)

        monkeypatch.setattr(ClassroomSingletonLock, "acquire", acquire)

        async def scenario():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=client.app, raise_app_exceptions=False),
                base_url="http://testserver",
            ) as browser:
                entered, release = asyncio.Event(), asyncio.Event()

                async def body():
                    entered.set()
                    await release.wait()
                    yield b"AAAA"

                first = asyncio.create_task(
                    browser.patch(
                        document["uploadUrl"],
                        headers={**authorization, "Upload-Offset": "0"},
                        content=body(),
                    )
                )
                await asyncio.wait_for(entered.wait(), 3)
                second = asyncio.create_task(
                    browser.patch(
                        document["uploadUrl"],
                        headers={**authorization, "Upload-Offset": "0"},
                        content=b"BBBB",
                    )
                )
                try:
                    assert await asyncio.to_thread(paused.wait, 3)
                    # The second dependency has read offset 0 but not acquired the
                    # native lock. Commit offset 4 before allowing acquisition.
                    release.set()
                    assert (await first).status_code == 202
                finally:
                    release.set()
                    allow_lock.set()
                assert (await second).status_code == 409
                assert (await browser.head(document["uploadUrl"], headers=authorization)).headers[
                    "Upload-Offset"
                ] == "4"

        asyncio.run(scenario())
