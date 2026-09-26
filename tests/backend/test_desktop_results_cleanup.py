import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from test_api import _client, _desktop_authorization
from wsi_viewer.database import session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import (
    AnalysisRun,
    ManagedResultAttachment,
    PathObjectMetadata,
    ResultDelivery,
    Slide,
)


@pytest.mark.parametrize("mode", ["success", "cleanup_denied", "invalid", "commit_denied"])
def test_results_archive_cleanup_follows_durable_success(
    tmp_path: Path, monkeypatch, caplog, mode: str
) -> None:
    slide_sha = "b" * 64
    attachment = b"synthetic result attachment"
    attachment_name = hashlib.sha256(attachment).hexdigest() + ".bin"
    documents = {
        "manifest.json": json.dumps(
            {
                "schema": "pathlab-private-results/v1",
                "artifactRevisionId": "revision-1",
                "slideSha256": slide_sha,
            }
        ).encode(),
        "runs.ndjson": b'{"id":"run-1"}\n',
        "objects.ndjson": (
            b'{"id":"object-1","runId":"run-1","type":"annotation",'
            b'"geometry":{"type":"point","x":10,"y":20}}\n'
        ),
        "measurements.ndjson": b"",
        "attachments/" + attachment_name: attachment,
    }
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, content in documents.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    bundle = stream.getvalue()
    with _client(tmp_path) as client:
        authorization = _desktop_authorization(client)
        settings = client.app.state.settings
        with session_factory(settings)() as database:
            slide = Slide(
                display_name="Synthetic results",
                original_filename="source.ome.tif",
                source_bytes=100,
                sha256=slide_sha,
                state=SlideState.READY_PRIVATE,
                slide_metadata={"width": 100, "height": 100},
            )
            database.add(slide)
            database.commit()
            slide_id = slide.id
        created = client.post(
            f"/api/v2/desktop/slides/{slide_id}/result-deliveries",
            headers=authorization,
            json={
                "artifactRevisionId": "revision-1",
                "slideSha256": slide_sha,
                "payloadLength": len(bundle),
                "payloadSha256": "a" * 64
                if mode == "invalid"
                else hashlib.sha256(bundle).hexdigest(),
                "schema": "pathlab-private-results/v1",
            },
        )
        assert created.status_code == 201
        delivery_id = created.json()["id"]
        target = settings.data_root / "staging" / "results" / f"{delivery_id}.plresults"
        original_unlink = Path.unlink
        attempted = []

        def deny_cleanup(path, *args, **kwargs):
            if path == target:
                with session_factory(settings)() as database:
                    assert database.get(ResultDelivery, delivery_id).status == "complete"
                attempted.append(path)
                raise PermissionError("synthetic archive lock")
            return original_unlink(path, *args, **kwargs)

        if mode == "cleanup_denied":
            monkeypatch.setattr(Path, "unlink", deny_cleanup)

        def reject_results_commit(database):
            if any(
                isinstance(item, ResultDelivery) and item.status == "complete"
                for item in database.dirty
            ):
                raise OSError("synthetic durable result commit failure")

        if mode == "commit_denied":
            event.listen(Session, "before_commit", reject_results_commit)
        try:
            uploaded = client.patch(
                created.json()["uploadUrl"],
                headers={**authorization, "Upload-Offset": "0"},
                content=bundle,
            )
        finally:
            if mode == "commit_denied":
                event.remove(Session, "before_commit", reject_results_commit)
        assert uploaded.status_code == 202
        failed = mode in {"invalid", "commit_denied"}
        expected_status = "failed" if failed else "complete"
        assert uploaded.json()["status"] == expected_status
        assert target.exists() == (mode != "success")
        if target.exists():
            assert target.read_bytes() == bundle
        for _ in range(2):
            repeated = client.patch(
                created.json()["uploadUrl"],
                headers={**authorization, "Upload-Offset": str(len(bundle))},
                content=b"",
            )
            assert repeated.status_code == 409
        status_url = f"/api/v2/desktop/slides/{slide_id}/result-deliveries/{delivery_id}"
        assert client.get(status_url, headers=authorization).json()["status"] == expected_status
        with session_factory(settings)() as database:
            assert database.scalar(select(func.count(AnalysisRun.id))) == (0 if failed else 1)
            assert database.scalar(select(func.count(PathObjectMetadata.id))) == (
                0 if failed else 1
            )
            assert database.scalar(select(func.count(ManagedResultAttachment.id))) == (
                0 if failed else 1
            )
            if not failed:
                assert database.scalar(select(PathObjectMetadata)).hidden is False
        if not failed:
            assert (
                settings.data_root / "results" / slide_id / attachment_name
            ).read_bytes() == attachment
            assert client.delete(status_url, headers=authorization).status_code == 409
        if mode == "cleanup_denied":
            assert attempted == [target]
            assert "DESKTOP_RESULTS_ARCHIVE_CLEANUP_FAILED" in caplog.text
            assert delivery_id in caplog.text
