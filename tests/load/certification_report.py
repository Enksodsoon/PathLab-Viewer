#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any


class ReportError(ValueError):
    pass


def _metric(summary: dict[str, Any], name: str, field: str) -> float:
    try:
        return float(summary["metrics"][name]["values"][field])
    except (KeyError, TypeError, ValueError) as error:
        raise ReportError(f"k6 summary is missing {name}.{field}") from error


def build_report(
    summary: dict[str, Any],
    observer: list[dict[str, Any]],
    browser: dict[str, Any],
    *,
    commit_sha: str,
) -> dict[str, Any]:
    if not observer:
        raise ReportError("host observation is empty")
    baseline_swap = int(observer[0]["swapUsedBytes"])
    baseline_restarts = int(observer[0]["restartCount"])
    metrics = {
        "requestFailureRate": _metric(summary, "http_req_failed", "rate"),
        "tileFailureRate": _metric(summary, "tile_failures", "rate"),
        "tileP95Ms": _metric(summary, "tile_latency", "p(95)"),
        "posterP95Ms": _metric(summary, "poster_latency", "p(95)"),
        "maxCpuPct": max(float(item["cpuPct"]) for item in observer),
        "maxMemoryPct": max(float(item["memoryPct"]) for item in observer),
        "swapGrowthBytes": max(int(item["swapUsedBytes"]) for item in observer)
        - baseline_swap,
        "restartGrowth": max(int(item["restartCount"]) for item in observer)
        - baseline_restarts,
        "oomObserved": any(item["oomKilled"] for item in observer),
        "servicesExact": all(item["servicesExact"] for item in observer),
        "readinessMaintained": all(item["ready"] for item in observer),
        "minDiskFreePct": min(float(item["diskFreePct"]) for item in observer),
        "releaseExact": all(item.get("releaseSha") == commit_sha for item in observer),
    }
    checks = {
        "requestFailures": metrics["requestFailureRate"] < 0.001,
        "tileFailures": metrics["tileFailureRate"] < 0.001,
        "tileLatency": metrics["tileP95Ms"] < 500,
        "posterLatency": metrics["posterP95Ms"] < 1500,
        "cpu": metrics["maxCpuPct"] < 80,
        "memory": metrics["maxMemoryPct"] < 85,
        "swap": metrics["swapGrowthBytes"] == 0,
        "restarts": metrics["restartGrowth"] == 0,
        "oom": metrics["oomObserved"] is False,
        "services": metrics["servicesExact"] is True,
        "readiness": metrics["readinessMaintained"] is True,
        "disk": metrics["minDiskFreePct"] >= 10,
        "release": metrics["releaseExact"] is True,
        "admin": browser.get("adminResponsive") is True,
        "conversion": browser.get("conversionSucceeded") is True,
        "cleanup": browser.get("cleanupSucceeded") is True,
        "degradedViewer": browser.get("degradedViewerRecovered") is True,
    }
    return {
        "schemaVersion": 1,
        "commit": commit_sha,
        "certified": all(checks.values()),
        "checks": checks,
        "metrics": metrics,
        "browser": {
            key: browser.get(key) is True
            for key in (
                "adminResponsive",
                "conversionSucceeded",
                "cleanupSucceeded",
                "degradedViewerRecovered",
            )
        },
    }


def markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# Capacity certification",
        "",
        f"- Commit: `{report['commit']}`",
        f"- Result: **{'PASS' if report['certified'] else 'FAIL'}**",
        "- Profile: 300 viewers (2 minute ramp, 10 minute hold, 1 minute ramp-down)",
        "",
        "| Measure | Result |",
        "| --- | ---: |",
        f"| Request failures | {metrics['requestFailureRate']:.4%} |",
        f"| Tile p95 | {metrics['tileP95Ms']:.1f} ms |",
        f"| Poster p95 | {metrics['posterP95Ms']:.1f} ms |",
        f"| Peak CPU | {metrics['maxCpuPct']:.1f}% |",
        f"| Peak memory | {metrics['maxMemoryPct']:.1f}% |",
        f"| Swap growth | {metrics['swapGrowthBytes']} bytes |",
        f"| Container restart growth | {metrics['restartGrowth']} |",
        "",
        "Only aggregate, non-identifying measurements are included.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build sanitized capacity evidence")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--observer", type=Path, required=True)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    observer = [
        json.loads(line)
        for line in args.observer.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    browser = json.loads(args.browser.read_text(encoding="utf-8"))
    report = build_report(summary, observer, browser, commit_sha=args.commit)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    if not report["certified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
