from __future__ import annotations

import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from scripts import generate_dependency_inventory as generator
from scripts.validate_dependency_inventory import DEFAULT_INVENTORY, validate

ROOT = Path(__file__).resolve().parents[2]


def test_inventory_reconciles_every_manifest() -> None:
    inventory = validate(DEFAULT_INVENTORY)
    assert len(inventory["records"]) >= 490


def test_inventory_rejects_an_explicit_different_requested_subject() -> None:
    inventory = json.loads(DEFAULT_INVENTORY.read_text())
    different = "0" * 40 if inventory["subjectCommit"] != "0" * 40 else "1" * 40
    with pytest.raises(ValueError, match="subject does not match requested commit"):
        validate(DEFAULT_INVENTORY, different)


def test_inventory_preserves_fail_closed_production_boundaries() -> None:
    records = {
        record["id"]: record for record in json.loads(DEFAULT_INVENTORY.read_text())["records"]
    }
    assert "npm:combine-errors@3.0.3" not in records
    assert records["npm:tus-js-client@4.3.1"]["license"] == "MIT"
    assert (
        records["model:trace-sim@2d625b1fad5c97584e1f7c69c3a95a6761fd934adaf17b1cecce329247e9fa0d"][
            "role"
        ]
        == "excluded-production"
    )
    assert records["terraform-provider:oracle/oci@7.32.0"]["admission"] == "BLOCKED"
    assert records["terraform-provider:oracle/oci@8.29.0-linux-arm64"]["admission"] == "BLOCKED"


def test_inventory_subject_is_current_implementation_tree() -> None:
    inventory = json.loads((ROOT / "docs/supply-chain/dependency-inventory.json").read_text())
    subject = inventory["subjectCommit"]
    tree = subprocess.check_output(
        ["git", "rev-parse", f"{subject}^{{tree}}"], cwd=ROOT, text=True
    ).strip()
    assert inventory["subjectTree"] == tree


def test_source_sha256_receipts_use_canonical_git_blob_bytes() -> None:
    inventory = json.loads(DEFAULT_INVENTORY.read_text())
    for receipt in inventory["sources"]:
        blob = subprocess.check_output(["git", "cat-file", "blob", receipt["gitBlob"]], cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest() == receipt["sha256"]


def _tar_member(name: str, payload: bytes) -> bytes:
    import io
    import tarfile

    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        member = tarfile.TarInfo(name)
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    return stream.getvalue()


def test_exact_embedded_readme_grants_are_recorded_without_admitting_mentions() -> None:
    from scripts.generate_dependency_inventory import archive_notices

    for name, version, member in [
        ("isarray", "1.0.0", "package/README.md"),
        ("splaytree", "3.2.3", "package/Readme.md"),
    ]:
        payload = (ROOT / "tests/fixtures/dependency-inventory" / f"{name}-README.txt").read_bytes()
        source = f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz"
        assert archive_notices(_tar_member(member, payload), source) == [
            {"path": member, "sha256": hashlib.sha256(payload).hexdigest()}
        ]
        assert archive_notices(_tar_member(member, payload + b"changed"), source) == []
        assert archive_notices(_tar_member(member, payload), "https://example.test/other.tgz") == []
        assert archive_notices(_tar_member(member, b"License: MIT"), source) == []
        assert archive_notices(_tar_member("package/OTHER.md", payload), source) == []


def test_python_inventory_selects_an_official_locked_wheel_over_unlocked_sdist(monkeypatch) -> None:
    import io
    import zipfile

    from scripts import generate_dependency_inventory as generator

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("pillow.dist-info/licenses/LICENSE", "Synthetic license notice")
    payload = stream.getvalue()
    checksum = hashlib.sha256(payload).hexdigest()
    metadata = {
        "info": {"license_expression": "MIT-CMU"},
        "urls": [
            {
                "packagetype": "sdist",
                "url": "https://example.test/pillow.tar.gz",
                "digests": {"sha256": "unlocked"},
            },
            {
                "packagetype": "bdist_wheel",
                "url": "https://example.test/pillow.whl",
                "digests": {"sha256": checksum},
            },
        ],
    }
    requested = []

    def read_url(url):
        requested.append(url)
        if url.endswith("/json"):
            return json.dumps(metadata).encode()
        return (
            _tar_member("LICENSE", b"Synthetic license notice")
            if url.endswith(".tar.gz")
            else payload
        )

    monkeypatch.setattr(generator, "read_url", read_url)
    record = generator.python_record(
        (
            "runtime-mandatory",
            ROOT / "deploy/backend-requirements.txt",
            {
                "name": "pillow",
                "version": "12.3.0",
                "hashes": [checksum],
            },
        )
    )
    assert record["artifact"] == "https://example.test/pillow.whl"
    assert record["checksumVerified"] is True
    assert record["noticeFiles"]
    assert record["admission"] == "RECORDED_UNREVIEWED"
    assert record["blockers"] == []
    assert "https://example.test/pillow.tar.gz" not in requested
    metadata["urls"][1]["digests"]["sha256"] = "not-locked"
    record = generator.python_record(
        (
            "runtime-mandatory",
            ROOT / "deploy/backend-requirements.txt",
            {
                "name": "pillow",
                "version": "12.3.0",
                "hashes": [checksum],
            },
        )
    )
    assert record["admission"] == "BLOCKED"
    assert "LOCK_HASH_OR_ARTIFACT_MISMATCH" in record["blockers"]


def test_exact_supplemental_notices_reject_wrong_artifact_missing_and_tampered_bytes(
    tmp_path, monkeypatch
):
    import copy

    import pytest

    from scripts import generate_dependency_inventory as generator

    manual = json.loads(generator.MANUAL_INPUTS.read_text())
    receipt = copy.deepcopy(manual["supplementalNotices"][0])
    for item in [receipt["packageReceipt"], *receipt["notices"]]:
        target = tmp_path / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / item["path"]).read_bytes())
    monkeypatch.setattr(generator, "ROOT", tmp_path)
    record = {key: receipt[key] for key in ("id", "source", "artifact", "checksum", "license")}
    record.update(checksumVerified=True, noticeFiles=[], admission="BLOCKED")
    record["name"] = "onnxruntime-common"
    record["version"] = "1.27.0"
    metadata = {"repository": {"url": receipt["repository"]}}
    result = generator.supplemental_notices(record, metadata, [receipt])
    assert result == [{"path": n["path"], "sha256": n["sha256"]} for n in receipt["notices"]]
    assert record["admission"] == "BLOCKED"
    for field in ("artifact", "checksum", "source", "license"):
        wrong = dict(record, **{field: "wrong"})
        with pytest.raises(ValueError, match="supplemental notice binding"):
            generator.supplemental_notices(wrong, metadata, [receipt])
    with pytest.raises(ValueError, match="supplemental notice binding"):
        generator.supplemental_notices(dict(record, checksumVerified=False), metadata, [receipt])
    with pytest.raises(ValueError, match="repository"):
        generator.supplemental_notices(
            record, {"repository": {"url": "https://example.test/other"}}, [receipt]
        )
    notice = tmp_path / receipt["notices"][0]["path"]
    original = notice.read_bytes()
    notice.write_bytes(original + b"tampered")
    with pytest.raises(ValueError, match="notice material checksum"):
        generator.supplemental_notices(record, metadata, [receipt])
    notice.unlink()
    with pytest.raises(FileNotFoundError):
        generator.supplemental_notices(record, metadata, [receipt])


def test_dependency_validator_rejects_forged_supplemental_binding(tmp_path):
    import copy

    import pytest

    from scripts import generate_dependency_inventory as generator

    inventory = json.loads(DEFAULT_INVENTORY.read_text())
    receipt = json.loads(generator.MANUAL_INPUTS.read_text())["supplementalNotices"][0]
    record = next(item for item in inventory["records"] if item["id"] == receipt["id"])
    record["supplementalNoticeSources"] = copy.deepcopy(receipt)
    record["noticeFiles"] = [{"path": n["path"], "sha256": n["sha256"]} for n in receipt["notices"]]
    record["artifact"] = "https://example.test/wrong-artifact.tgz"
    target = tmp_path / "inventory.json"
    target.write_text(json.dumps(inventory))
    with pytest.raises(ValueError, match="supplemental notice binding"):
        validate(target)
    del record["supplementalNoticeSources"]
    target.write_text(json.dumps(inventory))
    with pytest.raises(ValueError, match="local notice lacks supplemental notice binding"):
        validate(target)


@pytest.mark.parametrize("corrupt", [False, True])
def test_python_inventory_selects_locked_wheel_before_unlocked_sdist(monkeypatch, corrupt):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as wheel:
        wheel.writestr("example.dist-info/licenses/LICENSE", "Example license")
    data = archive.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    metadata = {
        "info": {"license_expression": "MIT"},
        "urls": [
            {"packagetype": "sdist", "url": "unlocked.tar.gz", "digests": {"sha256": "0" * 64}},
            {"packagetype": "bdist_wheel", "url": "locked.whl", "digests": {"sha256": digest}},
        ],
    }

    def read(url):
        assert url != "unlocked.tar.gz"
        if url == "locked.whl":
            return data + b"corrupt" if corrupt else data
        return json.dumps(metadata).encode()

    monkeypatch.setattr(generator, "read_url", read)
    record = generator.python_record(
        (
            "runtime-mandatory",
            ROOT / "deploy/backend-requirements.txt",
            {"name": "example", "version": "1", "hashes": [digest]},
        )
    )
    assert record["artifact"] == "locked.whl"
    assert record["checksumVerified"] is not corrupt
    assert ("LOCK_HASH_OR_ARTIFACT_MISMATCH" in record["blockers"]) is corrupt
