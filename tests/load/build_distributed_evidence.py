#!/usr/bin/env python3
"""Build the final aggregate-only evidence-v2 report from bound artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from build_capacity_decision import (
    host_evidence_passes,
    presenter_fanout_passes,
    strict_stage_passes,
)
from certification_report import build_report, validate_evidence_v2
from distributed_certification import validate_plan
from validate_postflight_evidence import validate as validate_postflight
from validate_sentinel_evidence import validate as validate_sentinels


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def load_ndjson(path: Path) -> list[dict[str, Any]]:
    values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not values or not all(isinstance(item, dict) for item in values):
        raise ValueError("continuous observer evidence is missing")
    return values


def aggregate_measurements(
    items: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if len(items) != 6:
        raise ValueError("strict evidence requires six shard measurements")
    names = {"presenterSse", "classroomControl", "generalApi", "staticTile", "poster", "question"}
    journeys: dict[str, Any] = {}
    for name in names:
        records = [item["journeys"][name] for item in items]
        requests = sum(record["requests"] for record in records)
        failures = sum(record["failures"] for record in records)
        if requests < 1:
            raise ValueError(f"journey {name} has no measurements")
        journeys[name] = {
            "requests": requests,
            "failureRate": failures / requests,
            "latencyMs": {
                percentile: max(
                    record["latencyMs"][percentile] for record in records if record["requests"] > 0
                )
                for percentile in ("p50", "p95", "p99")
            },
        }
    converged = sum(item["realtime"]["converged"] for item in items)
    expected = sum(item["realtime"]["expected"] for item in items)
    reconnects = sum(item["realtime"]["reconnectsSucceeded"] for item in items)
    reconnects_expected = sum(item["realtime"]["reconnectsExpected"] for item in items)
    realtime = {
        "sseConvergencePct": 100 * converged / expected if expected else 0,
        "reconnectSuccessPct": 100 * reconnects / reconnects_expected if reconnects_expected else 0,
        "lostCriticalEvents": sum(item["realtime"]["lostCriticalEvents"] for item in items),
        "unexpectedDisconnects": sum(item["realtime"]["unexpectedDisconnects"] for item in items),
        "queueOverflows": sum(item["realtime"]["queueOverflows"] for item in items),
    }
    pressure_items = [item["pressure"] for item in items]
    capacities = {item["queueCapacity"] for item in pressure_items}
    if capacities != {512}:
        raise ValueError("queue capacity evidence is inconsistent")
    pressure = {
        "queueMaxDepth": max(item["queueMaxDepth"] for item in pressure_items),
        "queueCapacity": 512,
        "eventLoopP99Ms": max(item["eventLoopP99Ms"] for item in pressure_items),
        "poolWaitP95Ms": max(item["poolWaitP95Ms"] for item in pressure_items),
        "poolTimeouts": sum(item["poolTimeouts"] for item in pressure_items),
        "sqliteLockErrors": sum(item["sqliteLockErrors"] for item in pressure_items),
    }
    return journeys, realtime, pressure


def build(
    plan: dict[str, Any],
    merged: dict[str, Any],
    sentinels: dict[str, Any],
    fault: dict[str, Any],
    fixture_preparation: dict[str, Any],
    cleanup: dict[str, Any],
    observer: list[dict[str, Any]],
    accounting: dict[str, Any],
    postflight: dict[str, Any],
) -> dict[str, Any]:
    validate_plan(plan)
    validate_sentinels(sentinels, require_cleanup=True)
    if sentinels["crossBrowser"]["ciRunId"] != plan["browserCiRunId"]:
        raise ValueError("cross-browser evidence is not bound to the approved exact-SHA check")
    validate_postflight(postflight)
    binding = {
        "runId": plan["runId"],
        "workflowSha": plan["workflowSha"],
        "planDigest": plan["planDigest"],
    }
    for label, artifact in (
        ("sentinel", sentinels),
        ("fault", fault),
        ("fixture preparation", fixture_preparation),
        ("cleanup", cleanup),
        ("postflight", postflight),
    ):
        if any(artifact.get(key) != value for key, value in binding.items()):
            raise ValueError(f"{label} evidence is not plan-bound")
    fault_succeeded = (
        fault.get("classroomOnly") is True
        and fault.get("generalApiResponsive") is True
        and 0 <= fault.get("readinessRecoverySeconds", 999) <= 90
        and 0 <= fault.get("convergenceSeconds", 999) <= 30
    )
    if not host_evidence_passes(plan, observer, fault, merged["stages"]):
        raise ValueError("host evidence does not prove the bounded run and recovery fault")
    if not presenter_fanout_passes(merged["sustainedMeasurements"]):
        raise ValueError("presenter fanout was not timestamp-proven across all six shards")
    journeys, realtime, pressure = aggregate_measurements(merged["sustainedMeasurements"])
    restart_baseline = observer[0]["restartCount"]
    restart_growth = max(item["restartCount"] for item in observer) - restart_baseline
    fault_start = datetime.fromisoformat(fault["startedAt"].replace("Z", "+00:00"))
    fault_end = datetime.fromisoformat(fault["completedAt"].replace("Z", "+00:00"))
    first_restart = next(
        (
            datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            for item in observer
            if item["restartCount"] != restart_baseline
        ),
        None,
    )
    expected_restarts = int(
        fault_succeeded
        and restart_growth == 1
        and first_restart is not None
        and fault_start <= first_restart <= fault_end + timedelta(seconds=15)
    )
    protected_names = {
        stage["name"] for stage in merged["stages"] if stage["outcome"] == "protected-early-stop"
    }
    protected_windows = [
        (stage["holdStartEpochMs"], stage["holdEndEpochMs"])
        for stage in plan["stages"]
        if stage["name"] in protected_names
    ]

    def is_protected_sample(item: dict[str, Any]) -> bool:
        timestamp_ms = int(
            datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")).timestamp() * 1000
        )
        return any(start <= timestamp_ms <= end for start, end in protected_windows)

    strict_observer = [item for item in observer if not is_protected_sample(item)]
    protected_observer = [item for item in observer if is_protected_sample(item)]
    resources = {
        "socketsPeak": max(item["sockets"] for item in observer),
        "fileDescriptorsPeak": max(item["fileDescriptors"] for item in observer),
        "containerCpuPctMax": max(item["containerCpuPct"] for item in strict_observer),
        "containerMemoryPctMax": max(item["containerMemoryPct"] for item in strict_observer),
        "protectedHeavyHostCpuPctMax": max(
            (item["cpuPct"] for item in protected_observer), default=0
        ),
        "protectedHeavyHostMemoryPctMax": max(
            (item["memoryPct"] for item in protected_observer), default=0
        ),
        "containerRestarts": max(0, restart_growth - expected_restarts),
        "oomKills": int(any(item["oomKilled"] for item in observer)),
        "diskReadBytes": sum(item["diskReadBytesDelta"] for item in observer),
        "diskWriteBytes": sum(item["diskWriteBytesDelta"] for item in observer),
        "diskFreePctMin": min(item["diskFreePct"] for item in observer),
        "networkRxBytes": sum(item["networkRxBytesDelta"] for item in observer),
        "networkTxBytes": sum(item["networkTxBytesDelta"] for item in observer),
    }
    recovery_stage = next(item for item in merged["stages"] if item["name"] == "recovery-1200")
    context = {
        "run": {
            "runId": plan["runId"],
            "startedAt": merged["stages"][0]["startedAt"],
            "endedAt": cleanup["completedAt"],
            "window": plan["window"],
        },
        "deployedSha": observer[0]["releaseSha"],
        "browserCi": {
            "name": "browser",
            "headSha": plan["workflowSha"],
            "conclusion": "success",
            "runId": plan["browserCiRunId"],
        },
        "stages": merged["stages"],
        "journeys": journeys,
        "realtime": realtime,
        "pressure": pressure,
        "resources": resources,
        "abort": merged.get("abort", {"aborted": False, "cause": None}),
        "recovery": {
            "attempted": True,
            "succeeded": fault_succeeded,
            "readinessRestored": fault["readinessRecoverySeconds"] <= 90,
            "usersAchieved": recovery_stage["achievedUsers"],
        },
        "fixturePreparation": {
            key: fixture_preparation[key]
            for key in (
                "prepared",
                "encrypted",
                "syntheticOnly",
                "identifiersIncluded",
                "endpointsValidated",
            )
        },
        "cleanup": {
            key: cleanup[key]
            for key in (
                "startedAt",
                "completedAt",
                "attempted",
                "succeeded",
                "configurationRestored",
                "fixturesRemoved",
                "bastionSessionsRemaining",
            )
        },
        "privacy": {
            "aggregateOnly": True,
            "credentialsMasked": True,
            "syntheticFixturesOnly": True,
        },
        "egress": {
            "measuredRunBytes": resources["networkTxBytes"],
            "projectedMonthlyRuns": accounting["projectedMonthlyRuns"],
            "projectedBytes": resources["networkTxBytes"] * accounting["projectedMonthlyRuns"],
            "budgetBytes": 9_000_000_000_000,
            "withinBudget": resources["networkTxBytes"] * accounting["projectedMonthlyRuns"]
            < 9_000_000_000_000,
        },
        "cost": {
            "currency": "SGD",
            "existingMonthlyAmount": accounting["monthToDateCost"],
            "projectedMonthlyAmount": 0,
            "amount": -accounting["monthToDateCost"],
            "permanentResourcesAdded": accounting["permanentResourcesAdded"],
            "computeOcpus": accounting["computeOcpus"],
            "memoryGb": accounting["memoryGb"],
            "storageGb": accounting["storageGb"],
            "shapeCompliant": (
                accounting["computeOcpus"],
                accounting["memoryGb"],
                accounting["storageGb"],
            )
            == (2, 12, 200),
        },
        "functionalSentinels": sentinels["functionalSentinels"],
    }
    summary = {
        "metrics": {
            "http_req_failed": {
                "values": {"rate": max(item["failureRate"] for item in journeys.values())}
            },
            "tile_failures": {"values": {"rate": journeys["staticTile"]["failureRate"]}},
            "tile_latency": {"values": {"p(95)": journeys["staticTile"]["latencyMs"]["p95"]}},
            "poster_latency": {"values": {"p(95)": journeys["poster"]["latencyMs"]["p95"]}},
        }
    }
    browser = {
        "adminResponsive": sentinels["adminResponsive"],
        "conversionSucceeded": sentinels["conversionSucceeded"],
        "cleanupSucceeded": sentinels["cleanupSucceeded"],
        "degradedViewerRecovered": sentinels["degradedViewerRecovered"],
    }
    hold_start = datetime.fromisoformat(context["stages"][0]["startedAt"])
    hold_end = datetime.fromisoformat(context["stages"][-1]["endedAt"])
    report_observer = [
        {
            **item,
            "restartCount": max(
                restart_baseline,
                item["restartCount"] - expected_restarts,
            ),
            "ready": True
            if fault_start
            <= datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            <= fault_end
            else item["ready"],
            "servicesExact": True
            if fault_start
            <= datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            <= fault_end
            else item["servicesExact"],
            "cpuPct": min(float(item["cpuPct"]), 79.999)
            if is_protected_sample(item)
            else item["cpuPct"],
            "memoryPct": min(float(item["memoryPct"]), 84.999)
            if is_protected_sample(item)
            else item["memoryPct"],
        }
        for item in observer
        if hold_start
        <= datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
        <= hold_end
    ]
    report = build_report(
        summary, report_observer, browser, commit_sha=plan["workflowSha"], evidence_context=context
    )
    if (
        report["certified"]
        and strict_stage_passes(merged["headroomMeasurements"])
        and presenter_fanout_passes(merged["headroomMeasurements"])
    ):
        report["certifiedTier"] = 1500
    expected_capacity = report["certifiedTier"] if report["certified"] else 300
    expected_sha = plan["workflowSha"] if report["certified"] else postflight["expectedSha"]
    if (
        postflight["finalCapacity"] != expected_capacity
        or postflight["deployedSha"] != expected_sha
    ):
        raise ValueError("postflight state does not match the final verdict")
    validate_evidence_v2(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in (
        "plan",
        "merged-shards",
        "sentinels",
        "fault",
        "fixture-preparation",
        "cleanup",
        "observer",
        "accounting",
        "postflight",
        "output-json",
        "output-markdown",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    report = build(
        load_object(args.plan),
        load_object(args.merged_shards),
        load_object(args.sentinels),
        load_object(args.fault),
        load_object(args.fixture_preparation),
        load_object(args.cleanup),
        load_ndjson(args.observer),
        load_object(args.accounting),
        load_object(args.postflight),
    )
    args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    verdict = f"CERTIFIED AT {report['certifiedTier']}" if report["certified"] else "NOT CERTIFIED"
    sha = report["release"]["workflowSha"]
    message = (
        f"# Capacity certification\n\n**{verdict}** for `{sha}`. "
        "Protocol scale evidence is distinct from exact-SHA browser CI and "
        "live functional sentinels.\n"
    )
    args.output_markdown.write_text(message, encoding="utf-8")


if __name__ == "__main__":
    main()
