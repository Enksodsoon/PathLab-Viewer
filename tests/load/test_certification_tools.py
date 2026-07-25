import json
import struct
from pathlib import Path

import pytest
from certification_report import build_report
from certification_watchdog import CertificationAbort, Watchdog, _consume_lines
from generate_synthetic_ome import generate_ome_tiff


def healthy_sample(**overrides: object) -> dict[str, object]:
    return {
        "ready": True,
        "cpuPct": 20,
        "memoryPct": 30,
        "swapUsedBytes": 0,
        "diskFreePct": 50,
        "servicesExact": True,
        "restartCount": 0,
        "oomKilled": False,
        "releaseSha": "a" * 40,
        **overrides,
    }


def test_watchdog_aborts_repeated_readiness_failure_and_swap_growth() -> None:
    watchdog = Watchdog()
    watchdog.observe_host(healthy_sample(ready=False))
    with pytest.raises(CertificationAbort, match="readiness"):
        watchdog.observe_host(healthy_sample(ready=False))

    watchdog = Watchdog()
    watchdog.observe_host(healthy_sample(swapUsedBytes=10))
    with pytest.raises(CertificationAbort, match="swap"):
        watchdog.observe_host(healthy_sample(swapUsedBytes=11))


def test_watchdog_applies_sustained_cpu_and_request_failure_limits() -> None:
    watchdog = Watchdog()
    for _ in range(2):
        watchdog.observe_host(healthy_sample(cpuPct=90))
    with pytest.raises(CertificationAbort, match="CPU"):
        watchdog.observe_host(healthy_sample(cpuPct=90))

    watchdog = Watchdog()
    for _ in range(99):
        watchdog.observe_request(0, elapsed_seconds=31)
    with pytest.raises(CertificationAbort, match="failure rate"):
        watchdog.observe_request(1, elapsed_seconds=31)


def test_watchdog_waits_for_complete_ndjson_records(tmp_path: Path) -> None:
    stream = tmp_path / "stream.ndjson"
    stream.write_text('{"ready":true}', encoding="utf-8")

    records, offset = _consume_lines(stream, 0)
    assert records == []
    assert offset == 0

    stream.write_text('{"ready":true}\n', encoding="utf-8")
    records, offset = _consume_lines(stream, offset)
    assert records == [{"ready": True}]
    assert offset == stream.stat().st_size


def test_synthetic_ome_tiff_has_classic_tiff_header_and_requested_size(tmp_path: Path) -> None:
    output = tmp_path / "synthetic.ome.tiff"
    generate_ome_tiff(output, width=100, height=50)

    content = output.read_bytes()
    assert content[:4] == b"II*\x00"
    ifd_offset = struct.unpack("<I", content[4:8])[0]
    assert ifd_offset == 8
    assert b"<OME " in content[:2048]
    assert output.stat().st_size >= 100 * 50 * 3


def test_report_contains_only_aggregate_fields_and_passes_healthy_run() -> None:
    summary = {
        "metrics": {
            "http_req_failed": {"values": {"rate": 0}},
            "tile_failures": {"values": {"rate": 0}},
            "tile_latency": {"values": {"p(95)": 100}},
            "poster_latency": {"values": {"p(95)": 200}},
        }
    }
    observer = [healthy_sample()]
    browser = {
        "adminResponsive": True,
        "conversionSucceeded": True,
        "cleanupSucceeded": True,
        "degradedViewerRecovered": True,
    }
    report = build_report(summary, observer, browser, commit_sha="a" * 40)

    assert report["certified"] is True
    serialized = json.dumps(report)
    assert "publicId" not in serialized
    assert "url" not in serialized.lower()
