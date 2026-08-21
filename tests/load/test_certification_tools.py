import json
import math
import struct
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from certification_report import (
    ReportError,
    build_report,
    validate_context_for_run,
    validate_evidence_v2,
)
from certification_watchdog import CertificationAbort, Watchdog, _consume_lines
from generate_synthetic_ome import generate_ome_tiff
from jsonschema import Draft202012Validator


def healthy_sample(
    timestamp: str = "2026-08-13T19:00:00Z", **overrides: object
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "ready": True,
        "cpuPct": 20,
        "memoryPct": 30,
        "swapUsedBytes": 0,
        "diskFreePct": 50,
        "networkRxBytesDelta": 1000,
        "networkTxBytesDelta": 1000,
        "diskReadBytesDelta": 1000,
        "diskWriteBytesDelta": 1000,
        "sockets": 100,
        "fileDescriptors": 200,
        "containerCpuPct": 20,
        "containerMemoryPct": 30,
        "servicesExact": True,
        "restartCount": 0,
        "classroomRestartCount": 0,
        "oomKilled": False,
        "releaseSha": "a" * 40,
        **overrides,
    }


def healthy_evidence_context() -> dict[str, object]:
    commit_sha = "a" * 40
    stages = [
        ("smoke-2", 2, 30, False),
        ("acceptance-100", 100, 600, False),
        ("boundary-300", 300, 600, False),
        ("boundary-600", 600, 600, False),
        ("boundary-900", 900, 600, False),
        ("sustained-1200", 1200, 3600, True),
        ("headroom-1500", 1500, 600, True),
        ("breakpoint-1750", 1750, 300, False),
        ("breakpoint-2000", 2000, 300, False),
        ("recovery-1200", 1200, 600, False),
    ]
    stage_started = datetime.fromisoformat("2026-08-14T02:00:00+07:00")
    stage_records = []
    for name, users, duration, strict in stages:
        stage_ended = stage_started + timedelta(seconds=duration)
        quotient, remainder = divmod(users, 6)
        shards = []
        for index in range(1, 7):
            shard_users = quotient + (1 if index <= remainder else 0)
            shards.append(
                {
                    "shardId": f"linux-{index}",
                    "targetUsers": shard_users,
                    "achievedUsers": shard_users,
                    "healthy": True,
                    "startEpochMs": int(stage_started.timestamp() * 1000) + index * 20,
                    "maxTimingDriftMs": index * 20,
                    "timingWithinTolerance": True,
                    "generator": {
                        "cpuPctMax": 35,
                        "memoryPctMax": 40,
                        "droppedIterations": 0,
                        "saturated": False,
                    },
                }
            )
        stage_records.append(
            {
                "name": name,
                "targetUsers": users,
                "achievedUsers": users,
                "startedAt": stage_started.isoformat(),
                "endedAt": stage_ended.isoformat(),
                "durationSeconds": duration,
                "strictGate": strict,
                "outcome": "passed",
                "abortCauses": [],
                "shards": shards,
            }
        )
        stage_started = stage_ended
    cleanup_ended = stage_started + timedelta(seconds=30)
    return {
        "run": {
            "runId": "capacity-run-123",
            "startedAt": "2026-08-14T02:00:00+07:00",
            "endedAt": cleanup_ended.isoformat(),
            "window": "2026-08-14T02:00:00+07:00/2026-08-14T05:00:00+07:00",
        },
        "deployedSha": commit_sha,
        "browserCi": {
            "name": "browser",
            "headSha": commit_sha,
            "conclusion": "success",
            "runId": 123456,
        },
        "stages": stage_records,
        "journeys": {
            name: {
                "requests": 1000,
                "failureRate": 0,
                "latencyMs": {"p50": 50, "p95": 100, "p99": 150},
            }
            for name in (
                "presenterSse",
                "classroomControl",
                "generalApi",
                "staticTile",
                "poster",
                "question",
            )
        },
        "realtime": {
            "sseConvergencePct": 100,
            "reconnectSuccessPct": 100,
            "lostCriticalEvents": 0,
            "unexpectedDisconnects": 0,
            "queueOverflows": 0,
        },
        "functionalSentinels": {
            "uploadConversion": True,
            "annotations": True,
            "libraryShare": True,
            "dynamicViewer": True,
            "desktop": True,
        },
        "pressure": {
            "queueMaxDepth": 100,
            "queueCapacity": 512,
            "eventLoopP99Ms": 80,
            "poolWaitP95Ms": 20,
            "poolTimeouts": 0,
            "sqliteLockErrors": 0,
        },
        "resources": {
            "socketsPeak": 2500,
            "fileDescriptorsPeak": 3000,
            "containerCpuPctMax": 70,
            "containerMemoryPctMax": 75,
            "protectedHeavyHostCpuPctMax": 0,
            "protectedHeavyHostMemoryPctMax": 0,
            "containerRestarts": 0,
            "oomKills": 0,
            "diskReadBytes": 1000000,
            "diskWriteBytes": 500000,
            "diskFreePctMin": 50,
            "networkRxBytes": 1000000,
            "networkTxBytes": 100000000,
        },
        "abort": {"aborted": False, "cause": None},
        "recovery": {
            "attempted": True,
            "succeeded": True,
            "readinessRestored": True,
            "usersAchieved": 1200,
        },
        "fixturePreparation": {
            "prepared": True,
            "encrypted": True,
            "syntheticOnly": True,
            "identifiersIncluded": False,
            "endpointsValidated": 4,
        },
        "cleanup": {
            "startedAt": stage_started.isoformat(),
            "completedAt": cleanup_ended.isoformat(),
            "attempted": True,
            "succeeded": True,
            "configurationRestored": True,
            "fixturesRemoved": True,
            "bastionSessionsRemaining": 0,
        },
        "privacy": {
            "aggregateOnly": True,
            "credentialsMasked": True,
            "syntheticFixturesOnly": True,
        },
        "egress": {
            "measuredRunBytes": 100000000,
            "projectedMonthlyRuns": 10,
            "projectedBytes": 1000000000,
            "budgetBytes": 9000000000000,
            "withinBudget": True,
        },
        "cost": {
            "currency": "SGD",
            "existingMonthlyAmount": 0,
            "projectedMonthlyAmount": 0,
            "amount": 0,
            "permanentResourcesAdded": False,
            "computeOcpus": 2,
            "memoryGb": 12,
            "storageGb": 200,
            "shapeCompliant": True,
        },
    }


def healthy_observer_samples(
    context: dict[str, object], *, gap_seconds: int = 10
) -> list[dict[str, object]]:
    run = context["run"]
    assert isinstance(run, dict)
    started = datetime.fromisoformat(str(run["startedAt"]))
    ended = datetime.fromisoformat(str(run["endedAt"]))
    samples = []
    current = started
    while current <= ended:
        utc = current.astimezone(UTC).isoformat().replace("+00:00", "Z")
        samples.append(healthy_sample(utc))
        current += timedelta(seconds=gap_seconds)
    if datetime.fromisoformat(samples[-1]["timestamp"].replace("Z", "+00:00")) < ended:
        samples.append(healthy_sample(ended.astimezone(UTC).isoformat().replace("+00:00", "Z")))
    return samples


def healthy_summary() -> dict[str, object]:
    return {
        "metrics": {
            "http_req_failed": {"values": {"rate": 0}},
            "tile_failures": {"values": {"rate": 0}},
            "tile_latency": {"values": {"p(95)": 100}},
            "poster_latency": {"values": {"p(95)": 200}},
        }
    }


def healthy_browser() -> dict[str, bool]:
    return {
        "adminResponsive": True,
        "conversionSucceeded": True,
        "cleanupSucceeded": True,
        "degradedViewerRecovered": True,
    }


def build_healthy_report() -> dict[str, object]:
    context = healthy_evidence_context()
    return build_report(
        healthy_summary(),
        healthy_observer_samples(context),
        healthy_browser(),
        commit_sha="a" * 40,
        evidence_context=context,
    )


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


def test_report_schema_v2_contains_every_approved_evidence_boundary() -> None:
    summary = {
        "metrics": {
            "http_req_failed": {"values": {"rate": 0}},
            "tile_failures": {"values": {"rate": 0}},
            "tile_latency": {"values": {"p(95)": 100}},
            "poster_latency": {"values": {"p(95)": 200}},
        }
    }
    context = healthy_evidence_context()
    observer = healthy_observer_samples(context)
    browser = {
        "adminResponsive": True,
        "conversionSucceeded": True,
        "cleanupSucceeded": True,
        "degradedViewerRecovered": True,
    }
    report = build_report(
        summary,
        observer,
        browser,
        commit_sha="a" * 40,
        evidence_context=context,
    )

    assert report["schemaVersion"] == 2
    assert report["certified"] is True
    assert set(report) == {
        "schemaVersion",
        "certified",
        "certifiedTier",
        "release",
        "browserCi",
        "run",
        "stages",
        "journeys",
        "realtime",
        "pressure",
        "resources",
        "abort",
        "recovery",
        "fixturePreparation",
        "cleanup",
        "privacy",
        "egress",
        "cost",
        "functionalSentinels",
        "checks",
        "metrics",
        "browser",
    }
    assert report["release"] == {
        "workflowSha": "a" * 40,
        "deployedSha": "a" * 40,
        "exact": True,
    }
    assert all(len(stage["shards"]) == 6 for stage in report["stages"])
    assert report["stages"][-1]["name"] == "recovery-1200"
    validate_evidence_v2(report)
    schema = json.loads(
        Path("tests/load/capacity-evidence-schema-v2.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)
    assert schema["$id"] == "https://pathlab.dev/schemas/capacity-evidence-v2.json"
    assert set(schema["required"]) == set(report)
    serialized = json.dumps(report)
    assert "publicId" not in serialized
    assert "url" not in serialized.lower()


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    [
        (("deployedSha", "b" * 40), "release"),
        (("browserCi", "headSha", "b" * 40), "browserCi"),
        (("browserCi", "conclusion", "failure"), "browserCi"),
        (("stages", 5, "shards", 0, "healthy", False), "shards"),
        (("stages", 5, "shards", 0, "generator", "saturated", True), "shards"),
        (("abort", "aborted", True), "abort"),
        (("recovery", "succeeded", False), "recovery"),
        (("cleanup", "configurationRestored", False), "cleanup"),
        (("cleanup", "fixturesRemoved", False), "cleanup"),
        (("cleanup", "bastionSessionsRemaining", 1), "cleanup"),
    ],
)
def test_schema_v2_fails_closed_for_invalid_certification_evidence(
    mutation: tuple[object, ...], failed_check: str
) -> None:
    context = deepcopy(healthy_evidence_context())
    target: object = context
    for key in mutation[:-2]:
        target = target[key]  # type: ignore[index]
    target[mutation[-2]] = mutation[-1]  # type: ignore[index]

    report = build_report(
        {
            "metrics": {
                "http_req_failed": {"values": {"rate": 0}},
                "tile_failures": {"values": {"rate": 0}},
                "tile_latency": {"values": {"p(95)": 100}},
                "poster_latency": {"values": {"p(95)": 200}},
            }
        },
        healthy_observer_samples(context),
        {
            "adminResponsive": True,
            "conversionSucceeded": True,
            "cleanupSucceeded": True,
            "degradedViewerRecovered": True,
        },
        commit_sha="a" * 40,
        evidence_context=context,
    )

    assert report["certified"] is False
    assert report["checks"][failed_check] is False


def test_schema_v2_rejects_missing_shards_and_non_aggregate_or_credential_data() -> None:
    summary = {
        "metrics": {
            "http_req_failed": {"values": {"rate": 0}},
            "tile_failures": {"values": {"rate": 0}},
            "tile_latency": {"values": {"p(95)": 100}},
            "poster_latency": {"values": {"p(95)": 200}},
        }
    }
    browser = {
        "adminResponsive": True,
        "conversionSucceeded": True,
        "cleanupSucceeded": True,
        "degradedViewerRecovered": True,
    }

    missing_shard = healthy_evidence_context()
    missing_shard["stages"][0]["shards"] = missing_shard["stages"][0]["shards"][:-1]  # type: ignore[index]
    with pytest.raises(ReportError, match="exactly six shards"):
        build_report(
            summary,
            healthy_observer_samples(missing_shard),
            browser,
            commit_sha="a" * 40,
            evidence_context=missing_shard,
        )

    sensitive = healthy_evidence_context()
    sensitive["participantToken"] = "secret-token"
    with pytest.raises(ReportError, match="unknown"):
        build_report(
            summary,
            healthy_observer_samples(sensitive),
            browser,
            commit_sha="a" * 40,
            evidence_context=sensitive,
        )


def test_schema_v2_requires_cleanup_evidence_instead_of_defaulting_to_success() -> None:
    context = healthy_evidence_context()
    del context["cleanup"]

    with pytest.raises(ReportError, match="cleanup"):
        build_report(
            {
                "metrics": {
                    "http_req_failed": {"values": {"rate": 0}},
                    "tile_failures": {"values": {"rate": 0}},
                    "tile_latency": {"values": {"p(95)": 100}},
                    "poster_latency": {"values": {"p(95)": 200}},
                }
            },
            healthy_observer_samples(context),
            {
                "adminResponsive": True,
                "conversionSucceeded": True,
                "cleanupSucceeded": True,
                "degradedViewerRecovered": True,
            },
            commit_sha="a" * 40,
            evidence_context=context,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        ("duration",),
        ("strictness",),
        ("window",),
        ("shard-total",),
        ("shard-sync",),
    ],
)
def test_schema_v2_rejects_fictitious_stage_timing_and_shard_claims(
    mutation: tuple[str],
) -> None:
    context = healthy_evidence_context()
    observer = healthy_observer_samples(context)
    stages = context["stages"]
    assert isinstance(stages, list)
    if mutation[0] == "duration":
        stages[5]["durationSeconds"] = 1
    elif mutation[0] == "strictness":
        stages[5]["strictGate"] = False
    elif mutation[0] == "window":
        run = context["run"]
        assert isinstance(run, dict)
        run["startedAt"] = "2026-08-14T12:00:00+07:00"
    elif mutation[0] == "shard-total":
        stages[6]["shards"][0]["targetUsers"] -= 1
    else:
        stages[6]["shards"][0]["startEpochMs"] += 5000

    with pytest.raises(ReportError):
        build_report(
            healthy_summary(),
            observer,
            healthy_browser(),
            commit_sha="a" * 40,
            evidence_context=context,
        )


def test_schema_v2_requires_continuous_bounded_observer_coverage() -> None:
    context = healthy_evidence_context()
    observer = healthy_observer_samples(context)
    del observer[len(observer) // 2]

    with pytest.raises(ReportError, match="observer.*gap"):
        build_report(
            healthy_summary(),
            observer,
            healthy_browser(),
            commit_sha="a" * 40,
            evidence_context=context,
        )


def test_context_preflight_binds_exact_browser_check_identity() -> None:
    context = healthy_evidence_context()
    validate_context_for_run(context, commit_sha="a" * 40, browser_ci_run_id=123456)

    with pytest.raises(ReportError, match="browser check identity"):
        validate_context_for_run(context, commit_sha="a" * 40, browser_ci_run_id=999999)


@pytest.mark.parametrize(
    ("section", "field", "invalid"),
    [
        ("journeys", "failureRate", -1),
        ("journeys", "p95", math.nan),
        ("pressure", "eventLoopP99Ms", math.inf),
        ("resources", "containerCpuPctMax", 101),
        ("egress", "projectedBytes", -1),
        ("cost", "amount", False),
        ("cost", "memoryGb", -12),
    ],
)
def test_schema_v2_rejects_invalid_numeric_domains(
    section: str, field: str, invalid: object
) -> None:
    context = healthy_evidence_context()
    if section == "journeys":
        journey = context["journeys"]["staticTile"]
        if field == "p95":
            journey["latencyMs"][field] = invalid
        else:
            journey[field] = invalid
    else:
        context[section][field] = invalid

    with pytest.raises(ReportError):
        build_report(
            healthy_summary(),
            healthy_observer_samples(context),
            healthy_browser(),
            commit_sha="a" * 40,
            evidence_context=context,
        )


@pytest.mark.parametrize("invalid", [-1, False, math.nan, math.inf])
def test_schema_v2_rejects_invalid_k6_or_observer_metrics(invalid: object) -> None:
    context = healthy_evidence_context()
    summary = healthy_summary()
    summary["metrics"]["http_req_failed"]["values"]["rate"] = invalid
    with pytest.raises(ReportError):
        build_report(
            summary,
            healthy_observer_samples(context),
            healthy_browser(),
            commit_sha="a" * 40,
            evidence_context=context,
        )

    observer = healthy_observer_samples(context)
    observer[0]["cpuPct"] = invalid
    with pytest.raises(ReportError):
        build_report(
            healthy_summary(),
            observer,
            healthy_browser(),
            commit_sha="a" * 40,
            evidence_context=context,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        ("checks", "cost", False),
        ("certified", False),
        ("release", "exact", False),
    ],
)
def test_semantic_validator_rejects_check_and_verdict_inconsistency(
    mutation: tuple[object, ...],
) -> None:
    report = build_healthy_report()
    target = report
    for key in mutation[:-2]:
        target = target[key]
    target[mutation[-2]] = mutation[-1]

    with pytest.raises(ReportError, match="semantic|certified|release"):
        validate_evidence_v2(report)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("run", "host", "10.0.0.1"),
        ("pressure", "note", "C:\\private\\capacity.txt"),
        ("cost", "value", "eyJhbGciOiJIUzI1NiJ9.payload.signature"),
        ("browserCi", "headers", "Bearer secret"),
        ("cleanup", "emailAddress", "teacher@example.org"),
        ("resources", "instance", "ocid1.instance.oc1..private"),
    ],
)
def test_schema_v2_rejects_every_nested_unknown_or_private_field(
    section: str, key: str, value: str
) -> None:
    context = healthy_evidence_context()
    context[section][key] = value

    with pytest.raises(ReportError, match="unknown|aggregate-only|schema"):
        build_report(
            healthy_summary(),
            healthy_observer_samples(context),
            healthy_browser(),
            commit_sha="a" * 40,
            evidence_context=context,
        )
