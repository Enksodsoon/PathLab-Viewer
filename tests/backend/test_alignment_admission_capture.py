"""Admission conformance through small byte fixtures; no models, decodes or services."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def producer():
    path = Path(__file__).resolve().parents[2] / "scripts/capture_alignment_admission.py"
    spec = importlib.util.spec_from_file_location("capture_admission", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_changed_bytes_during_fingerprint_are_refused(producer, tmp_path, monkeypatch):
    path = tmp_path / "source.bin"
    path.write_bytes(b"before")
    original = producer.hashlib.file_digest

    def changed(file, algorithm):
        result = original(file, algorithm)
        path.write_bytes(b"changed")
        return result

    monkeypatch.setattr(producer.hashlib, "file_digest", changed)
    with pytest.raises(ValueError, match="changed during read"):
        producer.fingerprint(path)


def test_loaded_cv2_binary_and_four_distributions_are_bound(producer, tmp_path, monkeypatch):
    binary = tmp_path / "cv2.pyd"
    binary.write_bytes(b"loaded49")
    fake = SimpleNamespace(__version__="4.9.0", _native=SimpleNamespace(__file__=str(binary)))
    monkeypatch.setitem(sys.modules, "cv2", fake)
    headless_version = ".".join(("4", "11", "0", "86"))
    contrib_version = ".".join(("4", "9", "0", "80"))
    metadata = {
        "opencv-python-headless": headless_version,
        "opencv-contrib-python-headless": contrib_version,
    }

    def version(name):
        if name not in metadata:
            raise producer.importlib.metadata.PackageNotFoundError(name)
        return metadata[name]

    monkeypatch.setattr(producer.importlib.metadata, "version", version)
    before = producer.runtime_identity()
    assert before["loadedCv2Version"] == "4.9.0"
    assert before["distributions"]["opencv-python"] is None
    assert before["distributions"]["opencv-contrib-python"] is None
    assert before["distributions"]["opencv-python-headless"] == headless_version
    fake.__version__ = "4.11.0"
    binary.write_bytes(b"loaded411")
    metadata["opencv-contrib-python-headless"] = headless_version
    after = producer.runtime_identity()
    assert after != before
    assert after["loadedCv2Binary"]["sha256"] != before["loadedCv2Binary"]["sha256"]
    assert (
        after["distributions"]["opencv-python-headless"]
        == before["distributions"]["opencv-python-headless"]
    )


def test_exact_clean_source_head_required(producer, monkeypatch):
    responses = iter(("reviewed\n", " M source.py\n"))
    monkeypatch.setattr(
        producer.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=next(responses))
    )
    with pytest.raises(ValueError, match="exact clean"):
        producer.source_state("reviewed")


def test_actual_base_interpreter_bytes_are_bound_even_when_venv_launcher_is_unchanged(
    producer, tmp_path, monkeypatch
):
    launcher, base, binary = (tmp_path / name for name in ("python.exe", "base.exe", "cv2.pyd"))
    launcher.write_bytes(b"unchanged-venv-redirector")
    base.write_bytes(b"base-before")
    binary.write_bytes(b"unchanged-cv2")
    monkeypatch.setattr(sys, "executable", str(launcher))
    monkeypatch.setattr(sys, "_base_executable", str(base))
    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(__version__="4.9.0", _native=SimpleNamespace(__file__=str(binary))),
    )
    monkeypatch.setattr(producer.importlib.metadata, "version", lambda name: "unchanged")
    before = producer.runtime_identity()
    base.write_bytes(b"base-after")
    after = producer.runtime_identity()
    assert before["executable"] == after["executable"]
    assert before["loadedCv2Binary"] == after["loadedCv2Binary"]
    assert before != after


def _warm_manifest(tmp_path):
    directory = tmp_path / "published"
    directory.mkdir()
    (directory / "thumbnail.jpg").write_bytes(b"original-encoded-pixels")
    size = [100, 80]
    digest = hashlib.sha256(
        b"thumbnail.jpgoriginal-encoded-pixels" + json.dumps(size).encode()
    ).hexdigest()
    document = {
        "pairs": [
            {
                "reference": {"path": str(directory), "size": size},
                "moving": {"path": str(directory), "size": size},
                "inputDigests": [digest, digest],
            }
        ]
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document))
    return path, directory, document


def test_warm_input_registered_pixels_and_frame_match_without_decoding(producer, tmp_path):
    manifest, directory, document = _warm_manifest(tmp_path)
    result = producer.warm_input_identity(manifest)
    assert len(result["uniqueInputs"]) == 1
    document["pairs"][0]["reference"]["size"] = [101, 80]
    manifest.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="bytes/geometry differ"):
        producer.warm_input_identity(manifest)
    document["pairs"][0]["reference"]["size"] = [100, 80]
    manifest.write_text(json.dumps(document))
    (directory / "thumbnail.jpg").write_bytes(b"changed-pixels")
    with pytest.raises(ValueError, match="bytes/geometry differ"):
        producer.warm_input_identity(manifest)


def test_resources_must_match_their_own_declared_name_not_any_ledger_hash(
    producer, tmp_path, monkeypatch
):
    executable = tmp_path / "var/valis-runtime/Scripts/python.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture-interpreter")
    monkeypatch.setattr(producer, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(producer, "source_state", lambda expected: {"head": expected})
    monkeypatch.setattr(producer, "RESOURCE_FILES", ("a.pth", "b.pth"))
    (tmp_path / "a.pth").write_bytes(b"official-b")
    (tmp_path / "b.pth").write_bytes(b"official-a")
    ledger = {
        "engines": [
            {
                "weights": [
                    {"name": "a.pth", "sha256": hashlib.sha256(b"official-a").hexdigest()},
                    {"name": "b.pth", "sha256": hashlib.sha256(b"official-b").hexdigest()},
                ]
            }
        ]
    }
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy/alignment-sources.json").write_text(json.dumps(ledger))
    with pytest.raises(ValueError, match="not admitted"):
        producer.capture("reviewed")


def test_terminal_changed_identity_is_persisted_then_fails(producer, tmp_path, monkeypatch):
    reference = tmp_path / "startup.json"
    reference.write_text(json.dumps({"identity": {"source": "original"}}))
    output = tmp_path / "terminal.json"
    monkeypatch.setattr(
        producer, "capture", lambda *args, **kwargs: {"identity": {"source": "changed"}}
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capture",
            "--expected-head",
            "reviewed",
            "--output",
            str(output),
            "--reference",
            str(reference),
        ],
    )
    with pytest.raises(ValueError, match="identity changed"):
        producer.main()
    receipt = json.loads(output.read_bytes())
    assert receipt["unchangedFromReference"] is False
    assert receipt["referenceSha256"] == producer.fingerprint(reference)["sha256"]
    with pytest.raises(FileExistsError):
        producer.main()
