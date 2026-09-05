"""Synthetic protocol conformance only. These fixtures are not measured receipts."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from capacity_evidence_v3 import (
    PARTITION,
    SUBJECT_FIELDS,
    TARGET,
    ProtocolError,
    digest,
    evaluate,
    finalize,
    seal,
    validate_finalized,
    validate_manifest,
)

NOW = 1_800_000_000_000
KEYS = {
    name: (name.encode() + b"-synthetic-test-only-") * 3
    for name in ("governance", "sensor", "meter", "restore", "admitter", "finalizer", "qualifier")
}
ROLES = {
    "governance": ["manifest", "current-context"],
    "sensor": ["interactions", "media", "resources", "clocks"],
    "meter": ["accounting"],
    "restore": ["restoration"],
    "admitter": ["generator"],
    "finalizer": ["capacity-result"],
    "qualifier": ["prerequisites"],
}
TRUST = {name: {"keyHex": key.hex(), "roles": ROLES[name]} for name, key in KEYS.items()}
ISSUER = {role: name for name, roles in ROLES.items() for role in roles}
D = "b" * 64


def sealed(kind, data, spec, *, issuer=None):
    owner = issuer or ISSUER[kind]
    return seal(
        kind,
        data,
        issuer=owner,
        key=KEYS[owner],
        manifest_digest=digest(spec),
        subject_value=spec["subject"],
    )


def package(n=3000, kind="combined", *, end=NOW - 60_000, campaign_id=None):
    start = end - (30_000 if kind == "reconnaissance" else 3_600_000)
    # Reconnaissance uses the same declared bounded faults and never earns a capacity.
    if kind == "reconnaissance":
        start = end - 600_000
    admission = start - 300_000
    frozen = admission - 60_000
    clients = {
        "contentDigest": D,
        "networkMatrixDigest": D,
        "fleetDigest": D,
        "cohortDigest": D,
        "samplingMethodDigest": D,
        "clockMethodDigest": D,
        "samplingIntervalMs": 100,
        "maxClockUncertaintyMs": 20,
        "directReceivers": n - n // 5,
        "turnReceivers": n // 5,
    }
    identity = {name: "a" * (40 if name == "releaseSha" else 64) for name in SUBJECT_FIELDS}
    identity.update(clientProfileDigest=digest(clients), resourcePartitionDigest=digest(PARTITION))
    spec = {
        "campaignId": campaign_id or kind,
        "subject": identity,
        "requestedTarget": TARGET.copy(),
        "campaignKind": kind,
        "learners": n,
        "frozenAtEpochMs": frozen,
        "admissionStartEpochMs": admission,
        "holdStartEpochMs": start,
        "holdEndEpochMs": end,
        "cleanupDeadlineEpochMs": end + 300_000,
        "expiresAtEpochMs": end + 3_600_000,
        "baselineAdmission": 300,
        "workload": {
            "instructors": 1,
            "staticDziCases": 6,
            "pointerHz": 10,
            "viewportHz": 10,
            "promptsPerLearner": 6,
            "questionLearners": math.ceil(n / 5),
            "reconnectLearners": math.ceil(n / 10),
        },
        "mediaProfile": {
            "videoCodec": "VP8",
            "videoHeight": 540,
            "videoCapBps": 600_000,
            "audioCodec": "Opus",
            "audioCapBps": 32_000,
            "publishers": 1,
            "receiveOnly": True,
            "transcoding": False,
            "recording": False,
            "wireEnvelopeBpsPerReceiver": 700_000,
            "wireEnvelopeEvidenceDigest": D,
        },
        "clientProfile": clients,
        "faultWindows": [
            {
                "kind": "live-restart",
                "startEpochMs": start + 100_000,
                "endEpochMs": start + 110_000,
            },
            {
                "kind": "media-failure",
                "startEpochMs": start + 200_000,
                "endEpochMs": start + 210_000,
            },
        ],
        "resourcePartition": PARTITION.copy(),
        "accountPolicyDigest": D,
        "sessionNonMediaBoundBytes": 1_000_000_000,
        "nonMediaBoundEvidenceDigest": D,
        "prerequisiteEvidenceDigests": {},
    }
    context = {
        "observedAtEpochMs": end + 50_000,
        "expiresAtEpochMs": end + 300_000,
        "currentOperatingAdmission": 300,
        "accountPolicyDigest": D,
    }
    window = {"startEpochMs": start, "endEpochMs": end}
    data = {
        "generator": {
            "admittedAtEpochMs": admission - 1000,
            "fleetDigest": D,
            "cohortDigest": D,
            "physicalClientEvidenceDigest": D,
            "learners": n,
            "independentAdmission": True,
            "saturated": False,
            "droppedIterations": 0,
            "receiptDigest": D,
        },
        "clocks": {
            **window,
            "methodDigest": D,
            "cohortDigest": D,
            "receiversCovered": n,
            "maxUncertaintyMs": 5,
            "beforeAndAfterProbes": True,
            "evidenceDigest": D,
        },
        "interactions": {
            **window,
            "learners": n,
            "cohortDigest": D,
            "admissionCompletedAtEpochMs": start - 1000,
            "caseTraversalsMinimum": 6,
            "promptAnswersMinimum": 6,
            "questionLearners": math.ceil(n / 5),
            "reconnectLearners": math.ceil(n / 10),
            "pointerHz": 10,
            "viewportHz": 10,
            "eventFanoutP95Ms": 100,
            "durableAckP95Ms": 200,
            "resyncP95Ms": 1000,
            "lostDurableInteractions": 0,
            "attendanceCorrect": True,
            "submittedWorkspaces": n,
            "finalConverged": n,
            "ephemeralRetained": 0,
            "guestDurableWrites": 0,
            "samplingMethodDigest": D,
            "minimumFanoutSamplesPerLearner": (end - start) // 1000,
            "fanoutObservationGapMsMaximum": 1000,
            "durableAckSamples": 7 * n + math.ceil(n / 5),
            "resyncSamples": math.ceil(n / 10),
            "faultsObserved": deepcopy(spec["faultWindows"]),
            "evidenceDigest": D,
        },
        "media": {
            **window,
            "learners": n,
            "cohortDigest": D,
            "receiversObserved": n,
            "decodedReceivers": n,
            "directReceivers": clients["directReceivers"],
            "turnReceivers": clients["turnReceivers"],
            "nonFaultObservationMsMinimum": end - start - 20_000,
            "jointDecodedMsMinimum": end - start - 20_000,
            "decodeIntervalsMaximum": 1,
            "startupP95Ms": 1000,
            "endToEndP95Ms": 500,
            "automaticRecoveryReceivers": n,
            "recoveredAtEpochMs": start + 209_000,
            "slidesOnlyReceivers": 0,
            "mediaProfileDigest": digest(spec["mediaProfile"]),
            "samplingMethodDigest": D,
            "transcodingObserved": False,
            "recordingObserved": False,
            "wireBpsPerReceiverMaximum": 650_000,
            "wireBytesObserved": 700_000_000,
            "samplesPerReceiverMinimum": math.ceil(
                (end - start - 20_000) / clients["samplingIntervalMs"]
            ),
            "sampleGapMsMaximum": clients["samplingIntervalMs"],
            "decodedVideoHeightMinimum": 540,
            "videoCodecObserved": "VP8",
            "audioCodecObserved": "Opus",
            "publisherVideoPayloadBpsMaximum": 600_000,
            "publisherAudioPayloadBpsMaximum": 32_000,
            "faultsObserved": deepcopy(spec["faultWindows"]),
            "evidenceDigest": D,
        },
        "resources": {
            **window,
            "partitionDigest": digest(PARTITION),
            "cgroupsEnforced": True,
            "residentPeakOcpus": 0.5,
            "residentPeakMemoryGiB": 2,
            "modePeakOcpus": 0.6,
            "modePeakMemoryGiB": 4,
            "emergencyHeadroomPreserved": True,
            "inactiveModesZero": True,
            "breaches": 0,
            "swapGrowthBytes": 0,
            "unexpectedRestarts": 0,
            "oomEvents": 0,
            "evidenceDigest": D,
        },
        "restoration": {
            "observedAtEpochMs": end + 10_000,
            "commandExitCode": 0,
            "releaseSha": identity["releaseSha"],
            "configurationDigest": identity["configurationDigest"],
            "finalAdmission": 300,
            "ready": True,
            "watchdogActive": True,
            "annotationsEnabled": False,
            "fixturesRemaining": 0,
            "ownBastionSessionsRemaining": 0,
            "otherCampaignsMutated": 0,
            "controllerRestored": True,
            "independentVerifier": True,
            "receiptDigest": D,
        },
    }

    def snapshot(timestamp, usage, sequence):
        return {
            "observedAtEpochMs": timestamp,
            "providerObservedAtEpochMs": timestamp - 1000,
            "providerUsageBytes": usage,
            "localUsageBytes": usage,
            "unreportedBytes": 0,
            "concurrentReservationsBytes": 1000,
            "trafficBytes": {
                "media": usage - 400,
                "tiles": 100,
                "backups": 100,
                "campaigns": 100,
                "other": 100,
            },
            "ledgerSequence": sequence,
            "reconciledWithoutLoss": True,
        }

    data["accounting"] = {
        "accountPolicyDigest": D,
        "accountIdentityDigest": D,
        "currency": "SGD",
        "tariffExpiresAtEpochMs": NOW + 86_400_000,
        "allowanceBytes": 10_000_000_000_000,
        "resetStartEpochMs": NOW - 30 * 86_400_000,
        "resetEndEpochMs": NOW + 86_400_000,
        "tariffDigest": D,
        "providerEvidenceDigest": D,
        "admissionSnapshot": snapshot(admission - 1000, 10_000, 1),
        "finalSnapshot": snapshot(end + 50_000, 1_000_010_000, 2),
        "essentialForecastBytes": 100_000_000,
        "reservation": {
            "campaignId": spec["campaignId"],
            "reservedAtEpochMs": admission - 1000,
            "durationSeconds": max(3600, math.ceil((end - (admission - 1000)) / 1000)),
            "reservedBytes": math.ceil(
                n * 700_000 * max(3600, math.ceil((end - (admission - 1000)) / 1000)) / 8
            )
            + 1_000_000_000,
            "actualSessionBytes": 1_000_000_000,
            "atomic": True,
            "durable": True,
            "exclusiveHeavyMode": True,
            "extensions": [],
            "enforcementCeilingBytes": 8_000_000_000_000,
            "receiptDigest": D,
        },
        "wireEnvelopeEvidenceDigest": D,
        "grossIncrementalCharge": 0,
        "grossPayment": 0,
        "projectedGrossIncrementalCharge": 0,
        "mandatoryPaidDependency": False,
        "localEnforcementProved": True,
        "durableStatePreserved": True,
    }
    policy_fields = {
        "accountIdentityDigest",
        "currency",
        "tariffDigest",
        "allowanceBytes",
        "resetStartEpochMs",
        "resetEndEpochMs",
        "tariffExpiresAtEpochMs",
    }
    policy_digest = digest({k: data["accounting"][k] for k in policy_fields})
    spec["accountPolicyDigest"] = context["accountPolicyDigest"] = policy_digest
    data["accounting"]["accountPolicyDigest"] = policy_digest
    if kind == "interaction-engineering":
        del data["media"]
    if kind == "media-engineering":
        del data["interactions"]
    if kind == "combined":
        priors = {}
        for name, prior_kind, offset in [
            ("interactionEngineering", "interaction-engineering", 8_000_000),
            ("mediaEngineering", "media-engineering", 4_000_000),
        ]:
            ps, pd, pc = package(n, prior_kind, end=frozen - offset, campaign_id=name.lower())
            pm, pr, current = envelopes(ps, pd, pc)
            result = finalize(
                pm,
                pr,
                current,
                TRUST,
                now_ms=ps["holdEndEpochMs"] + 60_000,
                issuer="finalizer",
                key=KEYS["finalizer"],
            )
            priors[name] = {
                "manifest": pm,
                "receipts": pr,
                "currentContext": current,
                "result": result,
            }
            spec["prerequisiteEvidenceDigests"][name] = digest(result)
        data["prerequisites"] = priors
    return spec, data, context


def envelopes(spec, data, context):
    return (
        sealed("manifest", spec, spec),
        [sealed(k, v, spec) for k, v in data.items()],
        sealed("current-context", context, spec),
    )


def assess(spec, data, context, **kwargs):
    return evaluate(*envelopes(spec, data, context), TRUST, now_ms=kwargs.get("now_ms", NOW))


@pytest.fixture
def healthy():
    return package()


def test_complete_combined_protocol_conformance_does_not_activate(healthy):
    result = assess(*healthy)
    assert result["combinedTargetResult"] == "SUCCESS", result
    assert result["qualifiedInteractionCapacity"] == 3000
    assert result["qualifiedMediaCapacity"] == 3000
    assert result["qualifiedCombinedCapacity"] == 3000
    assert result["currentOperatingAdmission"] == 300
    assert result["restorationResult"] == "PROVED"
    assert result["activationAllowed"] is False
    assert result["admissionChangeAuthorized"] is False


def test_lower_full_hold_is_qualified_at_its_count_but_target_unmet():
    result = assess(*package(300))
    assert result["combinedTargetResult"] == "PARTIAL", result
    assert result["qualifiedCombinedCapacity"] == 300
    assert result["requestedTarget"] == TARGET


def test_short_reconnaissance_never_qualifies_any_capacity():
    result = assess(*package(300, "reconnaissance"))
    assert result["combinedTargetResult"] == "PARTIAL", result
    assert result["qualifiedInteractionCapacity"] is None
    assert result["qualifiedMediaCapacity"] is None
    assert result["qualifiedCombinedCapacity"] is None


@pytest.mark.parametrize("kind", ["interaction-engineering", "media-engineering"])
def test_separate_engineering_campaigns_never_qualify_combined_target(kind):
    result = assess(*package(3000, kind))
    assert result["combinedTargetResult"] == "PARTIAL", result
    assert result["qualifiedCombinedCapacity"] is None


@pytest.mark.parametrize(
    "kind",
    [
        "generator",
        "clocks",
        "interactions",
        "media",
        "resources",
        "accounting",
        "restoration",
        "prerequisites",
    ],
)
def test_missing_measured_receipt_is_not_evaluable(healthy, kind):
    spec, data, context = healthy
    del data[kind]
    result = assess(spec, data, context)
    assert result["combinedTargetResult"] == "NOT_EVALUABLE", result
    assert result["qualifiedCombinedCapacity"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("learners", True),
        ("requestedTarget", {"learners": 300, "holdSeconds": 3600}),
        ("holdEndEpochMs", NOW - 100_000),
        ("baselineAdmission", 0),
        ("workload", {}),
        ("mediaProfile", {}),
        ("resourcePartition", {}),
        ("faultWindows", []),
        ("nonMediaBoundEvidenceDigest", None),
    ],
)
def test_frozen_manifest_cannot_be_relaxed_or_incomplete(healthy, field, value):
    spec, data, context = healthy
    spec[field] = value
    result = assess(spec, data, context)
    assert result["combinedTargetResult"] == "NOT_EVALUABLE"


@pytest.mark.parametrize(
    "field,value",
    [
        ("decodedReceivers", 2999),
        ("jointDecodedMsMinimum", 3_500_000),
        ("startupP95Ms", 5000),
        ("endToEndP95Ms", 2000),
        ("automaticRecoveryReceivers", 2999),
        ("slidesOnlyReceivers", 1),
        ("transcodingObserved", True),
        ("recordingObserved", True),
        ("wireBpsPerReceiverMaximum", 700_001),
        ("decodedVideoHeightMinimum", 360),
        ("videoCodecObserved", "H264"),
        ("publisherVideoPayloadBpsMaximum", 632_000),
        ("publisherAudioPayloadBpsMaximum", 33_000),
    ],
)
def test_observed_media_failures_never_pass(healthy, field, value):
    spec, data, context = healthy
    data["media"][field] = value
    result = assess(spec, data, context)
    assert result["combinedTargetResult"] == "NEGATIVE", result
    assert "MEDIA_WORKLOAD_FAILURE" in result["workloadFailures"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("receiversObserved", 2999),
        ("nonFaultObservationMsMinimum", 3_579_000),
        ("mediaProfileDigest", "c" * 64),
        ("samplingMethodDigest", "c" * 64),
        ("directReceivers", 3000),
        ("cohortDigest", "c" * 64),
        ("samplesPerReceiverMinimum", 1),
        ("sampleGapMsMaximum", 1001),
        ("jointDecodedMsMinimum", float("nan")),
    ],
)
def test_missing_or_drifted_receiver_evidence_is_unproved(healthy, field, value):
    spec, data, context = healthy
    data["media"][field] = value
    if isinstance(value, float) and math.isnan(value):
        with pytest.raises(ValueError):
            assess(spec, data, context)
    else:
        assert assess(spec, data, context)["combinedTargetResult"] == "NOT_EVALUABLE"


@pytest.mark.parametrize(
    "field,value",
    [
        ("caseTraversalsMinimum", 5),
        ("promptAnswersMinimum", 5),
        ("questionLearners", 599),
        ("reconnectLearners", 299),
        ("pointerHz", 9),
        ("viewportHz", 9),
        ("eventFanoutP95Ms", 1000),
        ("durableAckP95Ms", 2000),
        ("resyncP95Ms", 10000),
        ("lostDurableInteractions", 1),
        ("attendanceCorrect", False),
        ("submittedWorkspaces", 2999),
        ("finalConverged", 2999),
        ("ephemeralRetained", 1),
        ("guestDurableWrites", 1),
    ],
)
def test_observed_interaction_failure_is_negative(healthy, field, value):
    spec, data, context = healthy
    data["interactions"][field] = value
    result = assess(spec, data, context)
    assert result["combinedTargetResult"] == "NEGATIVE", result
    assert result["qualifiedCombinedCapacity"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("commandExitCode", 1),
        ("ready", False),
        ("finalAdmission", 3000),
        ("annotationsEnabled", True),
        ("fixturesRemaining", 1),
        ("ownBastionSessionsRemaining", 1),
        ("otherCampaignsMutated", 1),
        ("independentVerifier", False),
        ("watchdogActive", False),
    ],
)
def test_restoration_cannot_be_inferred_from_success_looking_fields(healthy, field, value):
    spec, data, context = healthy
    data["restoration"][field] = value
    result = assess(spec, data, context)
    assert result["restorationResult"] == "UNPROVED"
    assert result["combinedTargetResult"] == "NOT_EVALUABLE"


@pytest.mark.parametrize(
    "field,value",
    [
        ("modePeakOcpus", 1.01),
        ("residentPeakMemoryGiB", 3.01),
        ("modePeakMemoryGiB", 6.01),
        ("emergencyHeadroomPreserved", False),
        ("inactiveModesZero", False),
        ("breaches", 1),
        ("cgroupsEnforced", False),
        ("swapGrowthBytes", 1),
        ("oomEvents", 1),
    ],
)
def test_resource_partition_failure_blocks_qualification(healthy, field, value):
    spec, data, context = healthy
    data["resources"][field] = value
    result = assess(spec, data, context)
    assert result["combinedTargetResult"] == "NEGATIVE"
    assert result["qualifiedCombinedCapacity"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("grossIncrementalCharge", 0.01),
        ("grossPayment", 0.01),
        ("projectedGrossIncrementalCharge", 0.01),
        ("mandatoryPaidDependency", True),
        ("localEnforcementProved", False),
        ("allowanceBytes", 1_000_000_000_000),
        ("essentialForecastBytes", 9_500_000_000_000),
    ],
)
def test_zero_cash_gross_and_reserved_headroom_gates(healthy, field, value):
    spec, data, context = healthy
    data["accounting"][field] = value
    expected = "NOT_EVALUABLE" if field == "allowanceBytes" else "NEGATIVE"
    assert assess(spec, data, context)["combinedTargetResult"] == expected


@pytest.mark.parametrize(
    "damage",
    [
        "stale-provider",
        "reset",
        "concurrent",
        "unreported",
        "lost-category",
        "reservation",
        "atomic",
        "extension",
        "ledger-regression",
    ],
)
def test_accounting_unknowns_and_reservation_failures_deny_finalization(healthy, damage):
    spec, data, context = healthy
    p = data["accounting"]
    expected = "NOT_EVALUABLE"
    if damage == "stale-provider":
        p["finalSnapshot"]["providerObservedAtEpochMs"] -= 600_000
    elif damage == "reset":
        p["resetEndEpochMs"] = NOW - 1
    elif damage == "concurrent":
        p["admissionSnapshot"]["concurrentReservationsBytes"] = 9_000_000_000_000
        expected = "NEGATIVE"
    elif damage == "unreported":
        p["finalSnapshot"]["providerUsageBytes"] = 0
    elif damage == "lost-category":
        del p["finalSnapshot"]["trafficBytes"]["backups"]
    elif damage == "reservation":
        p["reservation"]["reservedBytes"] = 3000 * 632_000 * 3600 // 8
    elif damage == "atomic":
        p["reservation"]["atomic"] = False
    elif damage == "extension":
        p["reservation"]["extensions"] = [{"seconds": 60}]
    else:
        p["finalSnapshot"]["ledgerSequence"] = 1
    result = assess(spec, data, context)
    assert result["combinedTargetResult"] == expected, result


@pytest.mark.parametrize(
    "damage",
    [
        "signature",
        "v2",
        "wrong-subject",
        "duplicate",
        "untrusted",
        "stale-context",
        "changed-admission",
        "legacy-prerequisite",
    ],
)
def test_trust_and_current_release_inputs_fail_closed(healthy, damage):
    spec, data, context = healthy
    m, receipts, current = envelopes(spec, data, context)
    if damage == "signature":
        receipts[0]["signature"] = "0" * 64
    elif damage == "v2":
        m["schemaVersion"] = 2
    elif damage == "wrong-subject":
        receipts[0]["subject"]["hostDigest"] = "c" * 64
    elif damage == "duplicate":
        receipts.append(receipts[0])
    elif damage == "untrusted":
        receipts[0]["issuer"] = "unknown"
    elif damage == "stale-context":
        context["observedAtEpochMs"] -= 600_000
        current = sealed("current-context", context, spec)
    elif damage == "changed-admission":
        context["currentOperatingAdmission"] = 3000
        current = sealed("current-context", context, spec)
    else:
        data["prerequisites"]["interactionEngineering"]["result"]["schemaVersion"] = 2
        m, receipts, current = envelopes(spec, data, context)
    result = evaluate(m, receipts, current, TRUST, now_ms=NOW)
    assert result["combinedTargetResult"] == "NOT_EVALUABLE", result


def test_finalizer_recomputes_instead_of_trusting_signed_claim(healthy):
    m, receipts, current = envelopes(*healthy)
    final = finalize(
        m, receipts, current, TRUST, now_ms=NOW, issuer="finalizer", key=KEYS["finalizer"]
    )
    assert (
        validate_finalized(final, m, receipts, current, TRUST, now_ms=NOW)["combinedTargetResult"]
        == "SUCCESS"
    )
    final["payload"]["result"]["currentOperatingAdmission"] = 3000
    forged = sealed("capacity-result", final["payload"], healthy[0], issuer="finalizer")
    with pytest.raises(ProtocolError, match="INCONSISTENT"):
        validate_finalized(forged, m, receipts, current, TRUST, now_ms=NOW)


def test_finalizer_stores_digests_not_untrusted_receipt_contents(healthy):
    m, receipts, current = envelopes(*healthy)
    receipts[0]["privatePassword"] = "must-never-be-retained"
    final = finalize(
        m, receipts, current, TRUST, now_ms=NOW, issuer="finalizer", key=KEYS["finalizer"]
    )
    assert "must-never-be-retained" not in json.dumps(final)
    assert final["payload"]["result"]["combinedTargetResult"] == "NOT_EVALUABLE"


def test_cli_exposes_only_manifest_freeze_finalize_and_validation():
    path = Path(__file__).with_name("capacity_evidence_v3.py")
    result = subprocess.run([sys.executable, str(path), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "{freeze,finalize,validate}" in result.stdout
    assert "create-receipt" not in result.stdout


def test_cli_missing_evidence_emits_signed_not_evaluable_and_exit_two(healthy, tmp_path):
    manifest, _, current = envelopes(*healthy)
    files = {
        "manifest": manifest,
        "receipts": [],
        "current-context": current,
        "trusted-keys": TRUST,
    }
    arguments = []
    for name, content in files.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(content), encoding="utf-8")
        arguments.extend([f"--{name}", str(path)])
    key = tmp_path / "key"
    key.write_bytes(KEYS["finalizer"])
    output = tmp_path / "final.json"
    cli = [sys.executable, str(Path(__file__).with_name("capacity_evidence_v3.py"))]
    result = subprocess.run(
        [
            *cli,
            "finalize",
            *arguments,
            "--issuer",
            "finalizer",
            "--key-file",
            str(key),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    final = json.loads(output.read_text(encoding="utf-8"))
    assert final["payload"]["result"]["combinedTargetResult"] == "NOT_EVALUABLE"
    assert final["payload"]["result"]["qualifiedCombinedCapacity"] is None
    validation = subprocess.run(
        [*cli, "validate", *arguments, "--input", str(output)],
        capture_output=True,
        text=True,
    )
    assert validation.returncode == 2
    assert json.loads(validation.stdout)["combinedTargetResult"] == "NOT_EVALUABLE"


def test_bounded_faults_and_boolean_numeric_fields_are_strict(healthy):
    spec = healthy[0]
    spec["workload"]["instructors"] = True
    with pytest.raises(ProtocolError):
        validate_manifest(spec)
    spec["workload"]["instructors"] = 1
    spec["faultWindows"][0]["endEpochMs"] += 100_000
    with pytest.raises(ProtocolError):
        validate_manifest(spec)


@pytest.mark.parametrize("role", ["restoration", "generator"])
def test_independent_verifier_cannot_alias_sensor_key(healthy, role):
    spec, data, context = healthy
    m, receipts, current = envelopes(spec, data, context)
    trust = deepcopy(TRUST)
    owner = ISSUER[role]
    trust[owner]["keyHex"] = KEYS["sensor"].hex()
    receipts = [
        seal(
            role,
            data[role],
            issuer=owner,
            key=KEYS["sensor"],
            manifest_digest=digest(spec),
            subject_value=spec["subject"],
        )
        if item["kind"] == role
        else item
        for item in receipts
    ]
    result = evaluate(m, receipts, current, trust, now_ms=NOW)
    assert result["combinedTargetResult"] == "NOT_EVALUABLE"
    assert result["qualifiedCombinedCapacity"] is None


def test_unused_known_receipt_is_rejected():
    spec, data, context = package(kind="interaction-engineering")
    data["media"] = package()[1]["media"]
    assert assess(spec, data, context)["combinedTargetResult"] == "NOT_EVALUABLE"


@pytest.mark.parametrize(
    "kind,field,value",
    [
        ("interactions", "minimumFanoutSamplesPerLearner", 0),
        ("interactions", "durableAckSamples", 0),
        ("interactions", "resyncSamples", 0),
        ("interactions", "questionLearners", 10**18),
        ("interactions", "reconnectLearners", 10**18),
        ("media", "samplesPerReceiverMinimum", 0),
        ("media", "faultsObserved", []),
        ("generator", "saturated", True),
        ("generator", "droppedIterations", 1),
        ("accounting", "tariffExpiresAtEpochMs", NOW - 1),
        ("accounting", "accountIdentityDigest", "e" * 64),
        ("accounting", "currency", "USD"),
    ],
)
def test_missing_observation_or_account_authority_never_qualifies(healthy, kind, field, value):
    spec, data, context = healthy
    data[kind][field] = value
    result = assess(spec, data, context)
    assert result["combinedTargetResult"] == "NOT_EVALUABLE"
    assert result["failureCategory"] == "HARNESS_FAILURE"


def test_local_enforcement_ceiling_must_cover_committed_usage(healthy):
    spec, data, context = healthy
    data["accounting"]["reservation"]["enforcementCeilingBytes"] = 0
    assert assess(spec, data, context)["combinedTargetResult"] == "NEGATIVE"


def test_reservation_must_cover_admission_and_full_hold(healthy):
    spec, data, context = healthy
    data["accounting"]["reservation"]["durationSeconds"] = 3600
    result = assess(spec, data, context)
    assert result["combinedTargetResult"] == "NOT_EVALUABLE"
    assert result["qualifiedCombinedCapacity"] is None


def test_reservation_byte_bound_includes_admission_time(healthy):
    spec, data, context = healthy
    data["accounting"]["reservation"]["reservedBytes"] = (
        math.ceil(spec["learners"] * 700_000 * 3600 / 8) + spec["sessionNonMediaBoundBytes"]
    )
    assert assess(spec, data, context)["combinedTargetResult"] == "NOT_EVALUABLE"


def test_reservation_from_prior_allowance_period_is_not_current(healthy):
    spec, data, context = healthy
    p = data["accounting"]
    p["resetStartEpochMs"] = spec["admissionStartEpochMs"] - 500
    p["admissionSnapshot"]["observedAtEpochMs"] = spec["admissionStartEpochMs"]
    p["admissionSnapshot"]["providerObservedAtEpochMs"] = spec["admissionStartEpochMs"]
    policy = digest(
        {
            k: p[k]
            for k in (
                "accountIdentityDigest",
                "currency",
                "tariffDigest",
                "allowanceBytes",
                "resetStartEpochMs",
                "resetEndEpochMs",
                "tariffExpiresAtEpochMs",
            )
        }
    )
    spec["accountPolicyDigest"] = context["accountPolicyDigest"] = p["accountPolicyDigest"] = policy
    assert assess(spec, data, context)["combinedTargetResult"] == "NOT_EVALUABLE"


@pytest.mark.parametrize("snapshot", ["admissionSnapshot", "finalSnapshot"])
def test_provider_freshness_is_relative_to_admission_or_evaluation(healthy, snapshot):
    spec, data, context = healthy
    reference = spec["admissionStartEpochMs"] if snapshot == "admissionSnapshot" else NOW
    data["accounting"][snapshot]["observedAtEpochMs"] = reference - 50_000
    data["accounting"][snapshot]["providerObservedAtEpochMs"] = reference - 340_000
    assert assess(spec, data, context)["combinedTargetResult"] == "NOT_EVALUABLE"


@pytest.mark.parametrize(
    "kinds",
    [
        ("generator",),
        ("clocks",),
        ("interactions", "media"),
        ("generator", "clocks", "interactions", "media"),
    ],
)
def test_observation_cohort_must_match_frozen_admitted_roster(healthy, kinds):
    spec, data, context = healthy
    for kind in kinds:
        data[kind]["cohortDigest"] = "e" * 64
    result = assess(spec, data, context)
    assert result["combinedTargetResult"] == "NOT_EVALUABLE"
    assert result["qualifiedCombinedCapacity"] is None


def test_finalizer_rejects_even_signed_changed_subject(healthy):
    m, receipts, current = envelopes(*healthy)
    final = finalize(
        m, receipts, current, TRUST, now_ms=NOW, issuer="finalizer", key=KEYS["finalizer"]
    )
    modified_subject = dict(final["subject"], hostDigest="f" * 64)
    changed = seal(
        "capacity-result",
        final["payload"],
        issuer="finalizer",
        key=KEYS["finalizer"],
        manifest_digest=final["manifestDigest"],
        subject_value=modified_subject,
    )
    with pytest.raises(ProtocolError, match="SUBJECT"):
        validate_finalized(changed, m, receipts, current, TRUST, now_ms=NOW)
