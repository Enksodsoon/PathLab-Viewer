"""Atomic receipt replacement with actual owned Windows reader handles."""

import ctypes
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import pytest


@pytest.fixture(params=["operational", "warm"])
def writer(request):
    if request.param == "warm":
        from wsi_viewer.alignment_warm import _atomic_receipt

        return _atomic_receipt
    source = (
        Path(__file__).resolve().parents[2] / "scripts/measure_alignment_operational_profile.py"
    )
    spec = importlib.util.spec_from_file_location("operational_replacement", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._write


@pytest.fixture
def replacement():
    from wsi_viewer import alignment_artifacts

    return alignment_artifacts


def _reader(path, *, share_delete=False):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    share = 0x1 | 0x2 | (0x4 if share_delete else 0)
    handle = kernel.CreateFileW(str(path), 0x80000000, share, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    return kernel, handle


@pytest.mark.skipif(sys.platform != "win32", reason="actual Windows sharing semantics")
@pytest.mark.parametrize("share_delete", [False, True])
def test_reader_release_allows_same_pending_receipt(writer, tmp_path, share_delete):
    target = tmp_path / "receipt.json"
    writer(target, {"observation": 1})
    kernel, handle = _reader(target, share_delete=share_delete)
    released = threading.Event()
    pending_at_release = []

    def release():
        time.sleep(0.15)
        pending_at_release.extend(tmp_path.glob("*.pending"))
        assert kernel.CloseHandle(handle)
        released.set()

    thread = threading.Thread(target=release)
    thread.start()
    try:
        writer(target, {"observation": 2})
    finally:
        thread.join(2)
    assert released.is_set()
    assert len(pending_at_release) == 1
    assert json.loads(target.read_bytes()) == {"observation": 2}
    assert not list(tmp_path.glob("*.pending"))


@pytest.mark.skipif(sys.platform != "win32", reason="actual Windows sharing semantics")
def test_permanent_reader_preserves_old_and_pending_until_capped(writer, tmp_path):
    target = tmp_path / "receipt.json"
    writer(target, {"observation": 1})
    kernel, handle = _reader(target)
    started = time.monotonic()
    try:
        with pytest.raises(PermissionError) as raised:
            writer(target, {"observation": 2})
        elapsed = time.monotonic() - started
        assert raised.value.winerror in {5, 32, 33}
        assert 0.4 <= elapsed < 1.5
        assert json.loads(target.read_bytes()) == {"observation": 1}
        pending = list(tmp_path.glob("*.pending"))
        assert len(pending) == 1
        assert json.loads(pending[0].read_bytes()) == {"observation": 2}
    finally:
        assert kernel.CloseHandle(handle)


@pytest.mark.skipif(sys.platform != "win32", reason="actual Windows sharing semantics")
def test_writer_deadline_shortens_reader_retry(writer, tmp_path):
    target = tmp_path / "receipt.json"
    writer(target, {"observation": 1})
    kernel, handle = _reader(target)
    started = time.monotonic()
    try:
        with pytest.raises(PermissionError):
            writer(target, {"observation": 2}, deadline=started + 0.08)
        assert time.monotonic() - started < 0.3
        assert json.loads(target.read_bytes()) == {"observation": 1}
        assert len(list(tmp_path.glob("*.pending"))) == 1
    finally:
        assert kernel.CloseHandle(handle)


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_only_windows_transient_errors_retry_same_payload(
    replacement, monkeypatch, tmp_path, winerror
):
    pending, target = tmp_path / "one.pending", tmp_path / "receipt.json"
    pending.write_bytes(b"new payload")
    target.write_bytes(b"old payload")
    clock = [100.0]
    calls = []
    real_replace = replacement.os.replace
    error = PermissionError("injected transient sharing error")
    error.winerror = winerror

    def replace(source, destination):
        calls.append((source, destination, source.read_bytes()))
        if len(calls) < 3:
            raise error
        real_replace(source, destination)

    monkeypatch.setattr(replacement.sys, "platform", "win32")
    monkeypatch.setattr(replacement.os, "replace", replace)
    monkeypatch.setattr(replacement.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        replacement.time, "sleep", lambda value: clock.__setitem__(0, clock[0] + value)
    )
    replacement.replace_pending(pending, target)
    assert len(calls) == 3
    assert all(call == (pending, target, b"new payload") for call in calls)
    assert target.read_bytes() == b"new payload"


@pytest.mark.parametrize("platform,winerror", [("linux", 5), ("win32", 112), ("win32", None)])
def test_other_io_errors_never_retry(replacement, monkeypatch, tmp_path, platform, winerror):
    pending, target = tmp_path / "one.pending", tmp_path / "receipt.json"
    pending.write_bytes(b"new payload")
    target.write_bytes(b"old payload")
    error = OSError("injected nontransient I/O error")
    error.winerror = winerror
    calls = []

    def replace(*args):
        calls.append(args)
        raise error

    monkeypatch.setattr(replacement.sys, "platform", platform)
    monkeypatch.setattr(replacement.os, "replace", replace)
    monkeypatch.setattr(replacement.time, "sleep", lambda _: pytest.fail("unexpected retry sleep"))
    with pytest.raises(OSError) as raised:
        replacement.replace_pending(pending, target)
    assert raised.value is error
    assert calls == [(pending, target)]
    assert target.read_bytes() == b"old payload" and pending.read_bytes() == b"new payload"


def test_expired_deadline_allows_no_retry(replacement, monkeypatch, tmp_path):
    pending, target = tmp_path / "one.pending", tmp_path / "receipt.json"
    pending.write_bytes(b"new payload")
    error = PermissionError("injected sharing error")
    error.winerror = 5
    calls = []

    def replace(*args):
        calls.append(args)
        raise error

    monkeypatch.setattr(replacement.sys, "platform", "win32")
    monkeypatch.setattr(replacement.os, "replace", replace)
    monkeypatch.setattr(replacement.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(replacement.time, "sleep", lambda _: pytest.fail("deadline was extended"))
    with pytest.raises(PermissionError):
        replacement.replace_pending(pending, target, deadline=100.0)
    assert calls == [(pending, target)]
    assert pending.read_bytes() == b"new payload"


def test_sleep_reaching_deadline_allows_no_late_replace(replacement, monkeypatch, tmp_path):
    pending, target = tmp_path / "one.pending", tmp_path / "receipt.json"
    pending.write_bytes(b"new payload")
    target.write_bytes(b"old payload")
    error = PermissionError("injected sharing error")
    error.winerror = 5
    clock = [100.0]
    calls = []
    real_replace = replacement.os.replace

    def replace(source, destination):
        calls.append((source, destination))
        if len(calls) == 1:
            raise error
        real_replace(source, destination)

    monkeypatch.setattr(replacement.sys, "platform", "win32")
    monkeypatch.setattr(replacement.os, "replace", replace)
    monkeypatch.setattr(replacement.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(replacement.time, "sleep", lambda _: clock.__setitem__(0, 100.05))
    with pytest.raises(PermissionError) as raised:
        replacement.replace_pending(pending, target, deadline=100.05)
    assert raised.value is error
    assert calls == [(pending, target)]
    assert target.read_bytes() == b"old payload" and pending.read_bytes() == b"new payload"
