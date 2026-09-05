"""ADR 0132 protocol foundation. Produces evidence only; never changes admission."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import re
import time
from pathlib import Path
from typing import Any

PROTOCOL = "pathlab.combined-capacity/3"
TARGET = {"learners": 3000, "holdSeconds": 3600}
SUBJECT_FIELDS = {
    "releaseSha",
    "artifactDigest",
    "hostDigest",
    "configurationDigest",
    "clientProfileDigest",
    "resourcePartitionDigest",
    "installationDigest",
    "deploymentSelectionDigest",
}
PARTITION = {
    "hostOcpus": 2,
    "hostMemoryGiB": 12,
    "osMemoryGiB": 2,
    "residentOcpus": 0.75,
    "residentMemoryGiB": 3,
    "modeOcpus": 1,
    "modeMemoryGiB": 6,
    "emergencyOcpus": 0.25,
    "emergencyMemoryGiB": 1,
}
KINDS = {
    "manifest",
    "current-context",
    "generator",
    "clocks",
    "interactions",
    "media",
    "resources",
    "accounting",
    "restoration",
    "prerequisites",
    "capacity-result",
}
MAX_AGE_MS = 300_000
MAX_FAULT_MS = 90_000


class ProtocolError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition: Any, code: str) -> None:
    if not condition:
        raise ProtocolError(code)


def obj(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) == fields, label + "_FIELDS")
    return value


def number(value: Any, *, minimum: float = 0, maximum: float = 10**18) -> float:
    require(
        type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum,
        "NUMBER_INVALID",
    )
    return value


def integer(value: Any, *, minimum: int = 0, maximum: int = 10**18) -> int:
    number(value, minimum=minimum, maximum=maximum)
    require(type(value) is int, "INTEGER_REQUIRED")
    return value


def hex_digest(value: Any, size: int = 64) -> str:
    require(isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{size}}}", value), "DIGEST_INVALID")
    return value


def subject(value: Any) -> dict[str, Any]:
    value = obj(value, SUBJECT_FIELDS, "SUBJECT")
    for name, item in value.items():
        hex_digest(item, 40 if name == "releaseSha" else 64)
    return value


def seal(
    kind: str,
    payload: dict[str, Any],
    *,
    issuer: str,
    key: bytes,
    manifest_digest: str,
    subject_value: dict[str, Any],
) -> dict[str, Any]:
    """Low-level signing primitive; CLI never manufactures observation receipts."""
    require(kind in KINDS and len(key) >= 32, "SIGNING_INPUT_INVALID")
    value = {
        "schemaVersion": 3,
        "protocol": PROTOCOL,
        "kind": kind,
        "issuer": issuer,
        "manifestDigest": manifest_digest,
        "subject": subject_value,
        "payload": payload,
    }
    return {**value, "signature": hmac.new(key, canonical(value), hashlib.sha256).hexdigest()}


def verify(value: Any, kind: str, trust: dict[str, Any]) -> dict[str, Any]:
    value = obj(
        value,
        {
            "schemaVersion",
            "protocol",
            "kind",
            "issuer",
            "manifestDigest",
            "subject",
            "payload",
            "signature",
        },
        "ENVELOPE",
    )
    require(
        type(value["schemaVersion"]) is int
        and value["schemaVersion"] == 3
        and value["protocol"] == PROTOCOL
        and value["kind"] == kind,
        "V3_ENVELOPE_REQUIRED",
    )
    require(isinstance(value["issuer"], str) and value["issuer"] in trust, "ISSUER_UNTRUSTED")
    authority = obj(trust[value["issuer"]], {"keyHex", "roles"}, "TRUST")
    require(
        isinstance(authority["roles"], list) and kind in authority["roles"], "ISSUER_ROLE_DENIED"
    )
    key = bytes.fromhex(authority["keyHex"])
    require(len(key) >= 32, "TRUST_KEY_TOO_SHORT")
    hex_digest(value["signature"])
    unsigned = {k: v for k, v in value.items() if k != "signature"}
    expected = hmac.new(key, canonical(unsigned), hashlib.sha256).hexdigest()
    require(hmac.compare_digest(expected, value["signature"]), "SIGNATURE_INVALID")
    subject(value["subject"])
    hex_digest(value["manifestDigest"])
    require(isinstance(value["payload"], dict), "PAYLOAD_INVALID")
    return value["payload"]


def validate_manifest(value: Any) -> dict[str, Any]:
    value = obj(
        value,
        {
            "campaignId",
            "subject",
            "requestedTarget",
            "campaignKind",
            "learners",
            "frozenAtEpochMs",
            "admissionStartEpochMs",
            "holdStartEpochMs",
            "holdEndEpochMs",
            "cleanupDeadlineEpochMs",
            "expiresAtEpochMs",
            "baselineAdmission",
            "workload",
            "mediaProfile",
            "clientProfile",
            "faultWindows",
            "resourcePartition",
            "accountPolicyDigest",
            "sessionNonMediaBoundBytes",
            "nonMediaBoundEvidenceDigest",
            "prerequisiteEvidenceDigests",
        },
        "MANIFEST",
    )
    require(
        isinstance(value["campaignId"], str)
        and re.fullmatch("[a-z0-9-]{1,64}", value["campaignId"]),
        "CAMPAIGN_ID_INVALID",
    )
    subject(value["subject"])
    require(canonical(value["requestedTarget"]) == canonical(TARGET), "TARGET_CHANGED")
    require(
        value["campaignKind"]
        in {"combined", "interaction-engineering", "media-engineering", "reconnaissance"},
        "CAMPAIGN_KIND_INVALID",
    )
    n = integer(value["learners"], minimum=1, maximum=3000)
    integer(value["baselineAdmission"], minimum=1, maximum=3000)
    frozen, admission, start, end, cleanup, expires = [
        integer(value[k], minimum=1)
        for k in (
            "frozenAtEpochMs",
            "admissionStartEpochMs",
            "holdStartEpochMs",
            "holdEndEpochMs",
            "cleanupDeadlineEpochMs",
            "expiresAtEpochMs",
        )
    ]
    require(frozen < admission < start < end < cleanup <= expires, "WINDOW_ORDER_INVALID")
    require(start - admission <= 300_000, "ADMISSION_WINDOW_TOO_LONG")
    hold_ms = end - start
    if value["campaignKind"] != "reconnaissance":
        require(hold_ms == 3_600_000, "FULL_HOLD_REQUIRED")
    else:
        require(hold_ms <= 3_600_000, "RECONNAISSANCE_WINDOW_INVALID")
    require(cleanup - end >= 300_000, "INDEPENDENT_CLEANUP_RESERVE_MISSING")
    require(expires - cleanup <= 86_400_000, "QUALIFICATION_VALIDITY_TOO_LONG")
    expected_workload = {
        "instructors": 1,
        "staticDziCases": 6,
        "pointerHz": 10,
        "viewportHz": 10,
        "promptsPerLearner": 6,
        "questionLearners": math.ceil(n / 5),
        "reconnectLearners": math.ceil(n / 10),
    }
    require(canonical(value["workload"]) == canonical(expected_workload), "FROZEN_WORKLOAD_CHANGED")
    media = obj(
        value["mediaProfile"],
        {
            "videoCodec",
            "videoHeight",
            "videoCapBps",
            "audioCodec",
            "audioCapBps",
            "publishers",
            "receiveOnly",
            "transcoding",
            "recording",
            "wireEnvelopeBpsPerReceiver",
            "wireEnvelopeEvidenceDigest",
        },
        "MEDIA_PROFILE",
    )
    require(
        canonical({k: media[k] for k in media if not k.startswith("wireEnvelope")})
        == canonical(
            {
                "videoCodec": "VP8",
                "videoHeight": 540,
                "videoCapBps": 600_000,
                "audioCodec": "Opus",
                "audioCapBps": 32_000,
                "publishers": 1,
                "receiveOnly": True,
                "transcoding": False,
                "recording": False,
            }
        ),
        "MEDIA_PROFILE_CHANGED",
    )
    integer(media["wireEnvelopeBpsPerReceiver"], minimum=632_001)
    hex_digest(media["wireEnvelopeEvidenceDigest"])
    clients = obj(
        value["clientProfile"],
        {
            "contentDigest",
            "networkMatrixDigest",
            "fleetDigest",
            "cohortDigest",
            "samplingMethodDigest",
            "clockMethodDigest",
            "samplingIntervalMs",
            "maxClockUncertaintyMs",
            "directReceivers",
            "turnReceivers",
        },
        "CLIENT_PROFILE",
    )
    for name in clients:
        if name.endswith("Digest"):
            hex_digest(clients[name])
    require(
        digest(clients) == value["subject"]["clientProfileDigest"], "CLIENT_PROFILE_DIGEST_MISMATCH"
    )
    integer(clients["samplingIntervalMs"], minimum=1, maximum=1000)
    number(clients["maxClockUncertaintyMs"], maximum=100)
    minimum_path = 0 if value["campaignKind"] == "reconnaissance" else 1
    require(
        integer(clients["directReceivers"], minimum=minimum_path)
        + integer(clients["turnReceivers"], minimum=minimum_path)
        == n,
        "FROZEN_DIRECT_TURN_MIX_INVALID",
    )
    require(
        canonical(value["resourcePartition"]) == canonical(PARTITION), "RESOURCE_PARTITION_CHANGED"
    )
    require(
        digest(PARTITION) == value["subject"]["resourcePartitionDigest"],
        "PARTITION_DIGEST_MISMATCH",
    )
    faults = value["faultWindows"]
    require(isinstance(faults, list) and len(faults) == 2, "FROZEN_FAULTS_REQUIRED")
    for fault in faults:
        obj(fault, {"kind", "startEpochMs", "endEpochMs"}, "FAULT")
        begin = integer(fault["startEpochMs"])
        finish = integer(fault["endEpochMs"])
        require(
            start < begin < finish < end and finish - begin <= MAX_FAULT_MS, "FAULT_WINDOW_INVALID"
        )
    require({f["kind"] for f in faults} == {"live-restart", "media-failure"}, "FAULT_TYPES_INVALID")
    ordered = sorted(faults, key=lambda f: f["startEpochMs"])
    require(ordered[0]["endEpochMs"] <= ordered[1]["startEpochMs"], "FAULT_WINDOWS_OVERLAP")
    hex_digest(value["accountPolicyDigest"])
    integer(value["sessionNonMediaBoundBytes"], minimum=1)
    hex_digest(value["nonMediaBoundEvidenceDigest"])
    prior_digests = value["prerequisiteEvidenceDigests"]
    if value["campaignKind"] == "combined":
        obj(prior_digests, {"interactionEngineering", "mediaEngineering"}, "PREREQUISITE_DIGESTS")
        for item in prior_digests.values():
            hex_digest(item)
    else:
        require(prior_digests == {}, "ENGINEERING_PREREQUISITES_UNEXPECTED")
    return value


def _window(payload: dict[str, Any], manifest: dict[str, Any]) -> None:
    require(
        payload["startEpochMs"] == manifest["holdStartEpochMs"]
        and payload["endEpochMs"] == manifest["holdEndEpochMs"],
        "OBSERVATION_WINDOW_INCOMPLETE",
    )


def evaluate(
    manifest_envelope: Any, receipts: Any, current: Any, trust: dict[str, Any], *, now_ms: int
) -> dict[str, Any]:
    """Fail-closed assessment; only authenticated input receipts can earn capacity."""
    missing: list[str] = []
    failures: list[str] = []
    restored = "UNPROVED"
    interaction_capacity = media_capacity = combined_capacity = None
    operating = None
    manifest: dict[str, Any] = {}
    md = None
    sources: dict[str, dict[str, Any]] = {}
    issuers: dict[str, str] = {}
    try:
        manifest = validate_manifest(verify(manifest_envelope, "manifest", trust))
        md = digest(manifest)
        require(
            md == manifest_envelope["manifestDigest"]
            and manifest["subject"] == manifest_envelope["subject"],
            "MANIFEST_BINDING_INVALID",
        )
        ctx = obj(
            verify(current, "current-context", trust),
            {
                "observedAtEpochMs",
                "expiresAtEpochMs",
                "currentOperatingAdmission",
                "accountPolicyDigest",
            },
            "CURRENT_CONTEXT",
        )
        require(
            current["subject"] == manifest["subject"] and current["manifestDigest"] == md,
            "CURRENT_SUBJECT_DRIFT",
        )
        require(
            0 <= now_ms - integer(ctx["observedAtEpochMs"]) <= MAX_AGE_MS
            and now_ms < integer(ctx["expiresAtEpochMs"]),
            "CURRENT_CONTEXT_STALE",
        )
        require(
            ctx["accountPolicyDigest"] == manifest["accountPolicyDigest"], "ACCOUNT_POLICY_DRIFT"
        )
        operating = integer(ctx["currentOperatingAdmission"], minimum=1, maximum=3000)
        require(operating == manifest["baselineAdmission"], "OPERATING_ADMISSION_DRIFT")
        require(
            manifest["holdEndEpochMs"] <= now_ms <= manifest["expiresAtEpochMs"],
            "EVIDENCE_NOT_CURRENT",
        )
        require(isinstance(receipts, list), "RECEIPTS_REQUIRED")
        allowed = {"generator", "clocks", "resources", "accounting", "restoration"}
        if manifest["campaignKind"] != "media-engineering":
            allowed.add("interactions")
        if manifest["campaignKind"] != "interaction-engineering":
            allowed.add("media")
        if manifest["campaignKind"] == "combined":
            allowed.add("prerequisites")
        for receipt in receipts:
            require(
                isinstance(receipt, dict) and isinstance(receipt.get("kind"), str),
                "RECEIPT_INVALID",
            )
            kind = receipt["kind"]
            require(
                kind in allowed and kind not in sources,
                "RECEIPT_DUPLICATE_OR_UNEXPECTED",
            )
            payload = verify(receipt, kind, trust)
            require(
                receipt["manifestDigest"] == md and receipt["subject"] == manifest["subject"],
                "RECEIPT_SUBJECT_MISMATCH",
            )
            sources[kind] = payload
            issuers[kind] = receipt["issuer"]
    except (ValueError, TypeError, KeyError, OverflowError):
        missing.append("INPUT_AUTHENTICITY_OR_CONTRACT_UNPROVED")

    def checked(kind: str, fields: set[str]) -> dict[str, Any]:
        require(kind in sources, kind.upper() + "_MISSING")
        return obj(sources[kind], fields, kind.upper())

    def run_check(label: str, fn: Any) -> bool:
        try:
            return bool(fn())
        except (ValueError, TypeError, KeyError, OverflowError):
            missing.append(label + "_EVIDENCE_UNPROVED")
            return False

    def observed(condition: Any, label: str) -> bool:
        if not condition:
            failures.append(label)
        return bool(condition)

    def independent(kind: str) -> bool:
        verifier = issuers[kind]
        verifier_key = bytes.fromhex(trust[verifier]["keyHex"])
        return all(
            verifier != issuers[sensor]
            and verifier_key != bytes.fromhex(trust[issuers[sensor]]["keyHex"])
            for sensor in ("interactions", "media")
            if sensor in issuers
        )

    def restoration() -> bool:
        p = checked(
            "restoration",
            {
                "observedAtEpochMs",
                "commandExitCode",
                "releaseSha",
                "configurationDigest",
                "finalAdmission",
                "ready",
                "watchdogActive",
                "annotationsEnabled",
                "fixturesRemaining",
                "ownBastionSessionsRemaining",
                "otherCampaignsMutated",
                "controllerRestored",
                "independentVerifier",
                "receiptDigest",
            },
        )
        require(
            independent("restoration"),
            "RESTORATION_NOT_INDEPENDENT",
        )
        require(
            manifest["holdEndEpochMs"]
            <= integer(p["observedAtEpochMs"])
            <= min(now_ms, manifest["cleanupDeadlineEpochMs"]),
            "RESTORATION_WINDOW_INVALID",
        )
        hex_digest(p["receiptDigest"])
        return all(
            (
                integer(p["commandExitCode"]) == 0,
                p["releaseSha"] == manifest["subject"]["releaseSha"],
                p["configurationDigest"] == manifest["subject"]["configurationDigest"],
                integer(p["finalAdmission"]) == manifest["baselineAdmission"],
                p["ready"] is True,
                p["watchdogActive"] is True,
                p["annotationsEnabled"] is False,
                p["controllerRestored"] is True,
                p["independentVerifier"] is True,
                integer(p["fixturesRemaining"]) == 0,
                integer(p["ownBastionSessionsRemaining"]) == 0,
                integer(p["otherCampaignsMutated"]) == 0,
            )
        )

    authentic_inputs = not missing
    if run_check("RESTORATION", restoration):
        restored = "PROVED"
    else:
        missing.append("RESTORATION_UNPROVED")

    def generator() -> bool:
        p = checked(
            "generator",
            {
                "admittedAtEpochMs",
                "fleetDigest",
                "cohortDigest",
                "physicalClientEvidenceDigest",
                "learners",
                "independentAdmission",
                "saturated",
                "droppedIterations",
                "receiptDigest",
            },
        )
        hex_digest(p["physicalClientEvidenceDigest"])
        hex_digest(p["receiptDigest"])
        require(
            manifest["frozenAtEpochMs"]
            <= integer(p["admittedAtEpochMs"])
            <= manifest["admissionStartEpochMs"],
            "GENERATOR_ADMISSION_LATE",
        )
        require(
            p["fleetDigest"] == manifest["clientProfile"]["fleetDigest"]
            and p["cohortDigest"] == manifest["clientProfile"]["cohortDigest"]
            and integer(p["learners"]) == manifest["learners"]
            and p["independentAdmission"] is True,
            "GENERATOR_ADMISSION_UNPROVED",
        )
        require(
            independent("generator"),
            "GENERATOR_ADMISSION_NOT_INDEPENDENT",
        )
        require(
            p["saturated"] is False and integer(p["droppedIterations"]) == 0,
            "GENERATOR_SAFETY_FAILURE",
        )
        return True

    def clocks() -> bool:
        p = checked(
            "clocks",
            {
                "startEpochMs",
                "endEpochMs",
                "methodDigest",
                "cohortDigest",
                "receiversCovered",
                "maxUncertaintyMs",
                "beforeAndAfterProbes",
                "evidenceDigest",
            },
        )
        _window(p, manifest)
        hex_digest(p["evidenceDigest"])
        require(
            p["methodDigest"] == manifest["clientProfile"]["clockMethodDigest"]
            and p["cohortDigest"] == manifest["clientProfile"]["cohortDigest"]
            and integer(p["receiversCovered"]) == manifest["learners"]
            and p["beforeAndAfterProbes"] is True,
            "CLOCK_COVERAGE_MISSING",
        )
        require(
            number(p["maxUncertaintyMs"]) <= manifest["clientProfile"]["maxClockUncertaintyMs"],
            "CLOCK_UNCERTAINTY_EXCEEDED",
        )
        return True

    def interactions() -> bool:
        p = checked(
            "interactions",
            {
                "startEpochMs",
                "endEpochMs",
                "learners",
                "cohortDigest",
                "admissionCompletedAtEpochMs",
                "caseTraversalsMinimum",
                "promptAnswersMinimum",
                "questionLearners",
                "reconnectLearners",
                "pointerHz",
                "viewportHz",
                "eventFanoutP95Ms",
                "durableAckP95Ms",
                "resyncP95Ms",
                "lostDurableInteractions",
                "attendanceCorrect",
                "submittedWorkspaces",
                "finalConverged",
                "ephemeralRetained",
                "guestDurableWrites",
                "samplingMethodDigest",
                "minimumFanoutSamplesPerLearner",
                "fanoutObservationGapMsMaximum",
                "durableAckSamples",
                "resyncSamples",
                "faultsObserved",
                "evidenceDigest",
            },
        )
        _window(p, manifest)
        hex_digest(p["cohortDigest"])
        hex_digest(p["evidenceDigest"])
        require(
            p["cohortDigest"] == manifest["clientProfile"]["cohortDigest"],
            "INTERACTION_COHORT_CHANGED",
        )
        require(integer(p["learners"]) == manifest["learners"], "INTERACTION_COHORT_INCOMPLETE")
        require(p["faultsObserved"] == manifest["faultWindows"], "FAULT_OBSERVATION_MISMATCH")
        require(
            manifest["admissionStartEpochMs"]
            <= integer(p["admissionCompletedAtEpochMs"])
            <= manifest["holdStartEpochMs"],
            "ADMISSION_INCOMPLETE",
        )
        n = manifest["learners"]
        uncertainty = sources["clocks"]["maxUncertaintyMs"] * 2
        require(
            p["samplingMethodDigest"] == manifest["clientProfile"]["samplingMethodDigest"]
            and integer(p["minimumFanoutSamplesPerLearner"])
            >= (manifest["holdEndEpochMs"] - manifest["holdStartEpochMs"]) // 1000
            and number(p["fanoutObservationGapMsMaximum"]) <= 1000
            and integer(p["durableAckSamples"]) >= 7 * n + math.ceil(n / 5)
            and integer(p["resyncSamples"]) >= math.ceil(n / 10),
            "INTERACTION_METRIC_COVERAGE_MISSING",
        )
        return observed(
            all(
                (
                    integer(p["caseTraversalsMinimum"]) >= 6,
                    integer(p["promptAnswersMinimum"]) >= 6,
                    integer(p["questionLearners"], maximum=n) >= math.ceil(n / 5),
                    integer(p["reconnectLearners"], maximum=n) >= math.ceil(n / 10),
                    number(p["pointerHz"]) == 10,
                    number(p["viewportHz"]) == 10,
                    number(p["eventFanoutP95Ms"]) + uncertainty <= 1000,
                    number(p["durableAckP95Ms"]) + uncertainty <= 2000,
                    number(p["resyncP95Ms"]) + uncertainty <= 10_000,
                    integer(p["lostDurableInteractions"]) == 0,
                    p["attendanceCorrect"] is True,
                    integer(p["submittedWorkspaces"]) == n,
                    integer(p["finalConverged"]) == n,
                    integer(p["ephemeralRetained"]) == 0,
                    integer(p["guestDurableWrites"]) == 0,
                )
            ),
            "INTERACTION_WORKLOAD_FAILURE",
        )

    def media() -> bool:
        p = checked(
            "media",
            {
                "startEpochMs",
                "endEpochMs",
                "learners",
                "cohortDigest",
                "receiversObserved",
                "decodedReceivers",
                "directReceivers",
                "turnReceivers",
                "nonFaultObservationMsMinimum",
                "jointDecodedMsMinimum",
                "decodeIntervalsMaximum",
                "startupP95Ms",
                "endToEndP95Ms",
                "automaticRecoveryReceivers",
                "recoveredAtEpochMs",
                "slidesOnlyReceivers",
                "mediaProfileDigest",
                "samplingMethodDigest",
                "transcodingObserved",
                "recordingObserved",
                "wireBpsPerReceiverMaximum",
                "wireBytesObserved",
                "samplesPerReceiverMinimum",
                "sampleGapMsMaximum",
                "decodedVideoHeightMinimum",
                "videoCodecObserved",
                "audioCodecObserved",
                "publisherVideoPayloadBpsMaximum",
                "publisherAudioPayloadBpsMaximum",
                "faultsObserved",
                "evidenceDigest",
            },
        )
        _window(p, manifest)
        hex_digest(p["cohortDigest"])
        hex_digest(p["evidenceDigest"])
        n = manifest["learners"]
        integer(p["wireBytesObserved"], minimum=1)
        require(
            p["cohortDigest"] == manifest["clientProfile"]["cohortDigest"], "MEDIA_COHORT_CHANGED"
        )
        require(
            integer(p["learners"]) == n and integer(p["receiversObserved"]) == n,
            "RECEIVER_COVERAGE_MISSING",
        )
        require(
            p["mediaProfileDigest"] == digest(manifest["mediaProfile"])
            and p["samplingMethodDigest"] == manifest["clientProfile"]["samplingMethodDigest"],
            "MEDIA_PROFILE_OR_SAMPLING_CHANGED",
        )
        require(
            integer(p["directReceivers"]) == manifest["clientProfile"]["directReceivers"]
            and integer(p["turnReceivers"]) == manifest["clientProfile"]["turnReceivers"],
            "MEDIA_NETWORK_MIX_CHANGED",
        )
        excluded = sum(f["endEpochMs"] - f["startEpochMs"] for f in manifest["faultWindows"])
        nonfault = manifest["holdEndEpochMs"] - manifest["holdStartEpochMs"] - excluded
        require(
            integer(p["samplesPerReceiverMinimum"])
            >= math.ceil(nonfault / manifest["clientProfile"]["samplingIntervalMs"])
            and number(p["sampleGapMsMaximum"]) <= manifest["clientProfile"]["samplingIntervalMs"],
            "MEDIA_SAMPLE_COVERAGE_MISSING",
        )
        require(number(p["nonFaultObservationMsMinimum"]) == nonfault, "MEDIA_WINDOW_INCOMPLETE")
        require(p["faultsObserved"] == manifest["faultWindows"], "MEDIA_FAULT_WINDOWS_CHANGED")
        decoded = number(p["jointDecodedMsMinimum"], maximum=nonfault)
        intervals = integer(p["decodeIntervalsMaximum"], minimum=1)
        uncertainty = sources["clocks"]["maxUncertaintyMs"]
        conservative_decoded = (
            decoded
            - 2 * (manifest["clientProfile"]["samplingIntervalMs"] + uncertainty) * intervals
        )
        fault = next(f for f in manifest["faultWindows"] if f["kind"] == "media-failure")
        recovery_at = integer(p["recoveredAtEpochMs"])
        return observed(
            all(
                (
                    integer(p["decodedReceivers"]) == n,
                    conservative_decoded / nonfault >= 0.99,
                    number(p["startupP95Ms"]) + 2 * uncertainty <= 5000,
                    number(p["endToEndP95Ms"]) + 2 * uncertainty <= 2000,
                    integer(p["automaticRecoveryReceivers"]) == n,
                    fault["startEpochMs"] <= recovery_at <= fault["endEpochMs"],
                    integer(p["slidesOnlyReceivers"]) == 0,
                    p["transcodingObserved"] is False,
                    p["recordingObserved"] is False,
                    integer(p["decodedVideoHeightMinimum"]) == 540,
                    p["videoCodecObserved"] == "VP8",
                    p["audioCodecObserved"] == "Opus",
                    number(p["publisherVideoPayloadBpsMaximum"]) <= 600_000,
                    number(p["publisherAudioPayloadBpsMaximum"]) <= 32_000,
                    number(p["wireBpsPerReceiverMaximum"], minimum=1)
                    <= manifest["mediaProfile"]["wireEnvelopeBpsPerReceiver"],
                )
            ),
            "MEDIA_WORKLOAD_FAILURE",
        )

    def resources() -> bool:
        p = checked(
            "resources",
            {
                "startEpochMs",
                "endEpochMs",
                "partitionDigest",
                "cgroupsEnforced",
                "residentPeakOcpus",
                "residentPeakMemoryGiB",
                "modePeakOcpus",
                "modePeakMemoryGiB",
                "emergencyHeadroomPreserved",
                "inactiveModesZero",
                "breaches",
                "swapGrowthBytes",
                "unexpectedRestarts",
                "oomEvents",
                "evidenceDigest",
            },
        )
        _window(p, manifest)
        hex_digest(p["evidenceDigest"])
        require(p["partitionDigest"] == digest(PARTITION), "RESOURCE_PARTITION_MISMATCH")
        return observed(
            all(
                (
                    p["cgroupsEnforced"] is True,
                    number(p["residentPeakOcpus"]) <= 0.75,
                    number(p["residentPeakMemoryGiB"]) <= 3,
                    number(p["modePeakOcpus"]) <= 1,
                    number(p["modePeakMemoryGiB"]) <= 6,
                    p["emergencyHeadroomPreserved"] is True,
                    p["inactiveModesZero"] is True,
                    integer(p["breaches"]) == 0,
                    integer(p["swapGrowthBytes"]) == 0,
                    integer(p["unexpectedRestarts"]) == 0,
                    integer(p["oomEvents"]) == 0,
                )
            ),
            "HOST_RESOURCE_PARTITION_FAILURE",
        )

    def accounting() -> bool:
        p = checked(
            "accounting",
            {
                "accountPolicyDigest",
                "accountIdentityDigest",
                "currency",
                "tariffExpiresAtEpochMs",
                "allowanceBytes",
                "resetStartEpochMs",
                "resetEndEpochMs",
                "tariffDigest",
                "providerEvidenceDigest",
                "admissionSnapshot",
                "finalSnapshot",
                "essentialForecastBytes",
                "reservation",
                "wireEnvelopeEvidenceDigest",
                "grossIncrementalCharge",
                "grossPayment",
                "projectedGrossIncrementalCharge",
                "mandatoryPaidDependency",
                "localEnforcementProved",
                "durableStatePreserved",
            },
        )
        require(
            p["accountPolicyDigest"] == manifest["accountPolicyDigest"], "ACCOUNT_POLICY_MISMATCH"
        )
        policy_fields = {
            "accountIdentityDigest",
            "currency",
            "tariffDigest",
            "allowanceBytes",
            "resetStartEpochMs",
            "resetEndEpochMs",
            "tariffExpiresAtEpochMs",
        }
        require(
            digest({k: p[k] for k in policy_fields}) == p["accountPolicyDigest"],
            "ACCOUNT_POLICY_CONTENT_MISMATCH",
        )
        hex_digest(p["accountIdentityDigest"])
        require(
            isinstance(p["currency"], str) and re.fullmatch("[A-Z]{3}", p["currency"]),
            "CURRENCY_UNPROVED",
        )
        require(
            integer(p["tariffExpiresAtEpochMs"]) > max(now_ms, manifest["cleanupDeadlineEpochMs"]),
            "TARIFF_EXPIRED",
        )
        for name in ("tariffDigest", "providerEvidenceDigest", "wireEnvelopeEvidenceDigest"):
            hex_digest(p[name])
        require(
            p["wireEnvelopeEvidenceDigest"]
            == manifest["mediaProfile"]["wireEnvelopeEvidenceDigest"],
            "WIRE_ENVELOPE_UNQUALIFIED",
        )
        allowance = integer(p["allowanceBytes"], minimum=1)
        reset_start, reset_end = integer(p["resetStartEpochMs"]), integer(p["resetEndEpochMs"])
        require(
            reset_start
            <= manifest["admissionStartEpochMs"]
            < manifest["cleanupDeadlineEpochMs"]
            < reset_end
            and now_ms < reset_end,
            "ALLOWANCE_RESET_CROSSED",
        )
        essential = integer(p["essentialForecastBytes"])
        reserve = max((allowance + 4) // 5, essential)
        snapshots = []
        for name, reference in (
            ("admissionSnapshot", manifest["admissionStartEpochMs"]),
            ("finalSnapshot", now_ms),
        ):
            s = obj(
                p[name],
                {
                    "observedAtEpochMs",
                    "providerObservedAtEpochMs",
                    "providerUsageBytes",
                    "localUsageBytes",
                    "unreportedBytes",
                    "concurrentReservationsBytes",
                    "trafficBytes",
                    "ledgerSequence",
                    "reconciledWithoutLoss",
                },
                "ACCOUNT_SNAPSHOT",
            )
            timestamp = integer(s["observedAtEpochMs"])
            require(
                0 <= reference - timestamp <= MAX_AGE_MS
                and 0 <= reference - integer(s["providerObservedAtEpochMs"]) <= MAX_AGE_MS
                and s["providerObservedAtEpochMs"] <= timestamp,
                "ACCOUNTING_STALE",
            )
            require(
                reset_start <= s["providerObservedAtEpochMs"] < reset_end,
                "ACCOUNTING_WRONG_RESET_PERIOD",
            )
            traffic = obj(
                s["trafficBytes"],
                {"media", "tiles", "backups", "campaigns", "other"},
                "TRAFFIC_ACCOUNTING",
            )
            require(
                sum(integer(v) for v in traffic.values()) == integer(s["localUsageBytes"])
                and s["reconciledWithoutLoss"] is True,
                "LEDGER_USAGE_UNPROVED",
            )
            require(
                integer(s["unreportedBytes"])
                >= max(0, s["localUsageBytes"] - integer(s["providerUsageBytes"])),
                "UNREPORTED_USAGE_DROPPED",
            )
            integer(s["concurrentReservationsBytes"])
            integer(s["ledgerSequence"], minimum=1)
            snapshots.append(s)
        before, after = snapshots
        require(
            after["observedAtEpochMs"] >= manifest["holdEndEpochMs"]
            and after["providerUsageBytes"] >= before["providerUsageBytes"],
            "ACCOUNTING_REGRESSED",
        )
        require(
            after["ledgerSequence"] > before["ledgerSequence"]
            and after["localUsageBytes"] >= before["localUsageBytes"],
            "LEDGER_REGRESSED",
        )
        reservation = obj(
            p["reservation"],
            {
                "campaignId",
                "reservedAtEpochMs",
                "durationSeconds",
                "reservedBytes",
                "actualSessionBytes",
                "atomic",
                "durable",
                "exclusiveHeavyMode",
                "extensions",
                "enforcementCeilingBytes",
                "receiptDigest",
            },
            "RESERVATION",
        )
        hex_digest(reservation["receiptDigest"])
        require(
            reservation["campaignId"] == manifest["campaignId"]
            and manifest["frozenAtEpochMs"]
            <= integer(reservation["reservedAtEpochMs"])
            <= manifest["admissionStartEpochMs"]
            and reservation["atomic"] is True
            and reservation["durable"] is True
            and reservation["exclusiveHeavyMode"] is True,
            "RESERVATION_NOT_ADMITTED",
        )
        require(reservation["extensions"] == [], "EXTENSION_REQUIRES_NEW_RESERVATION")
        duration = integer(reservation["durationSeconds"], minimum=3600)
        reservation_end = reservation["reservedAtEpochMs"] + duration * 1000
        require(
            reset_start <= reservation["reservedAtEpochMs"]
            and manifest["holdEndEpochMs"] <= reservation_end < reset_end
            and reservation_end < p["tariffExpiresAtEpochMs"],
            "RESERVATION_WINDOW_UNCOVERED",
        )
        bound_bytes = (
            manifest["learners"] * manifest["mediaProfile"]["wireEnvelopeBpsPerReceiver"] * duration
            + 7
        ) // 8 + manifest["sessionNonMediaBoundBytes"]
        reserved = integer(reservation["reservedBytes"])
        require(reserved >= bound_bytes, "RESERVATION_UNDERBOUNDED")
        committed_before = (
            max(before["providerUsageBytes"], before["localUsageBytes"])
            + before["unreportedBytes"]
            + before["concurrentReservationsBytes"]
            + reserved
        )
        committed_after = (
            max(after["providerUsageBytes"], after["localUsageBytes"])
            + after["unreportedBytes"]
            + after["concurrentReservationsBytes"]
        )
        require(
            after["localUsageBytes"] - before["localUsageBytes"]
            >= integer(reservation["actualSessionBytes"]),
            "SESSION_USAGE_NOT_RECONCILED",
        )
        if "media" in sources:
            require(
                reservation["actualSessionBytes"] >= sources["media"]["wireBytesObserved"],
                "MEASURED_MEDIA_USAGE_NOT_RECONCILED",
            )
        return observed(
            all(
                (
                    committed_before + reserve <= allowance,
                    committed_after + reserve <= allowance,
                    committed_after <= integer(reservation["enforcementCeilingBytes"]),
                    integer(reservation["actualSessionBytes"]) <= reserved,
                    integer(reservation["enforcementCeilingBytes"]) <= allowance - reserve,
                    number(p["grossIncrementalCharge"]) == 0,
                    number(p["grossPayment"]) == 0,
                    number(p["projectedGrossIncrementalCharge"]) == 0,
                    p["mandatoryPaidDependency"] is False,
                    p["localEnforcementProved"] is True,
                    p["durableStatePreserved"] is True,
                )
            ),
            "ZERO_CASH_ADMISSION_FAILURE",
        )

    def prerequisites() -> bool:
        p = checked("prerequisites", {"interactionEngineering", "mediaEngineering"})
        ids = []
        for name in p:
            prior = obj(
                p[name],
                {"manifest", "receipts", "currentContext", "result"},
                "ENGINEERING_PREREQUISITE",
            )
            prior_manifest = validate_manifest(verify(prior["manifest"], "manifest", trust))
            expected_kind = (
                "interaction-engineering"
                if name == "interactionEngineering"
                else "media-engineering"
            )
            require(prior_manifest["campaignKind"] == expected_kind, "ENGINEERING_KIND_INVALID")
            signed_result = verify(prior["result"], "capacity-result", trust)["result"]
            evaluated_at = integer(signed_result["evaluatedAtEpochMs"])
            prior_result = validate_finalized(
                prior["result"],
                prior["manifest"],
                prior["receipts"],
                prior["currentContext"],
                trust,
                now_ms=evaluated_at,
            )
            capacity_field = (
                "qualifiedInteractionCapacity"
                if name == "interactionEngineering"
                else "qualifiedMediaCapacity"
            )
            require(
                prior_manifest["campaignId"] != manifest["campaignId"]
                and evaluated_at < manifest["frozenAtEpochMs"]
                and prior_manifest["subject"] == manifest["subject"]
                and integer(prior_result[capacity_field]) >= manifest["learners"]
                and prior_result["restorationResult"] == "PROVED"
                and prior_result["missingEvidence"] == []
                and prior_result["workloadFailures"] == []
                and digest(prior["result"]) == manifest["prerequisiteEvidenceDigests"][name],
                "ENGINEERING_PREREQUISITE_UNQUALIFIED",
            )
            ids.append(prior_manifest["campaignId"])
        require(len(set(ids)) == 2, "SEPARATE_ENGINEERING_CAMPAIGNS_REQUIRED")
        return True

    if authentic_inputs:
        generator_ok = run_check("GENERATOR", generator)
        clock_ok = run_check("CLOCK", clocks)
        resource_ok = run_check("RESOURCE", resources)
        accounting_ok = run_check("ACCOUNTING", accounting)
        full = manifest["campaignKind"] != "reconnaissance"
        interaction_ok = media_ok = False
        if clock_ok and manifest["campaignKind"] != "media-engineering":
            interaction_ok = run_check("INTERACTION", interactions)
        if clock_ok and manifest["campaignKind"] != "interaction-engineering":
            media_ok = run_check("MEDIA", media)
        common = (
            generator_ok and clock_ok and resource_ok and accounting_ok and restored == "PROVED"
        )
        if common and full and interaction_ok:
            interaction_capacity = manifest["learners"]
        if common and full and media_ok:
            media_capacity = manifest["learners"]
        if manifest["campaignKind"] == "combined":
            prior_ok = run_check("PREREQUISITE", prerequisites)
            cohorts_match = (
                interaction_ok
                and media_ok
                and sources["interactions"]["cohortDigest"] == sources["media"]["cohortDigest"]
            )
            if interaction_ok and media_ok and not cohorts_match:
                missing.append("COMBINED_COHORT_MISMATCH")
            if common and full and cohorts_match and prior_ok:
                combined_capacity = manifest["learners"]
    if missing:
        result = "NOT_EVALUABLE"
        category = "HARNESS_FAILURE"
        combined_capacity = None
    elif failures:
        result = "NEGATIVE"
        category = "WORKLOAD_FAILURE"
    elif combined_capacity == TARGET["learners"]:
        result = "SUCCESS"
        category = None
    else:
        result = "PARTIAL"
        category = None
    return {
        "schemaVersion": 3,
        "protocol": PROTOCOL,
        "requestedTarget": TARGET.copy(),
        "manifestDigest": md,
        "subject": manifest.get("subject"),
        "campaignKind": manifest.get("campaignKind"),
        "evaluatedAtEpochMs": now_ms,
        "qualifiedInteractionCapacity": interaction_capacity,
        "qualifiedMediaCapacity": media_capacity,
        "qualifiedCombinedCapacity": combined_capacity,
        "currentOperatingAdmission": operating,
        "combinedTargetResult": result,
        "failureCategory": category,
        "missingEvidence": sorted(set(missing)),
        "workloadFailures": sorted(set(failures)),
        "restorationResult": restored,
        "activationAllowed": False,
        "admissionChangeAuthorized": False,
    }


def finalize(
    manifest: Any,
    receipts: Any,
    current: Any,
    trust: dict[str, Any],
    *,
    now_ms: int,
    issuer: str,
    key: bytes,
) -> dict[str, Any]:
    result = evaluate(manifest, receipts, current, trust, now_ms=now_ms)
    payload = {
        "result": result,
        "sourceManifestDigest": digest(manifest),
        "sourceReceiptsDigest": digest(receipts),
        "currentContextDigest": digest(current),
    }
    final = seal(
        "capacity-result",
        payload,
        issuer=issuer,
        key=key,
        manifest_digest=result["manifestDigest"] or "0" * 64,
        subject_value=result["subject"]
        or {k: "0" * (40 if k == "releaseSha" else 64) for k in SUBJECT_FIELDS},
    )
    verify(final, "capacity-result", trust)
    return final


def validate_finalized(
    value: Any, manifest: Any, receipts: Any, current: Any, trust: dict[str, Any], *, now_ms: int
) -> dict[str, Any]:
    payload = obj(
        verify(value, "capacity-result", trust),
        {"result", "sourceManifestDigest", "sourceReceiptsDigest", "currentContextDigest"},
        "FINALIZED",
    )
    require(payload["currentContextDigest"] == digest(current), "FINALIZER_CURRENT_CONTEXT_CHANGED")
    require(
        payload["sourceManifestDigest"] == digest(manifest)
        and payload["sourceReceiptsDigest"] == digest(receipts),
        "FINALIZER_SOURCE_CHANGED",
    )
    result = evaluate(manifest, receipts, current, trust, now_ms=now_ms)
    previous = dict(payload["result"])
    previous["evaluatedAtEpochMs"] = now_ms
    require(previous == result, "FINALIZER_RESULT_INCONSISTENT_OR_STALE")
    require(
        value["manifestDigest"] == (result["manifestDigest"] or "0" * 64),
        "FINALIZER_BINDING_INVALID",
    )
    expected_subject = result["subject"] or {
        k: "0" * (40 if k == "releaseSha" else 64) for k in SUBJECT_FIELDS
    }
    require(value["subject"] == expected_subject, "FINALIZER_SUBJECT_MISMATCH")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze", help="Sign an explicitly supplied declarative manifest")
    freeze.add_argument("--spec", type=Path, required=True)
    for name in ("finalize", "validate"):
        command = commands.add_parser(name)
        command.add_argument("--current-context", type=Path, required=True)
        command.add_argument("--trusted-keys", type=Path, required=True)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--receipts", type=Path, required=True)
        if name == "validate":
            command.add_argument("--input", type=Path, required=True)
    for command in (freeze, commands.choices["finalize"]):
        command.add_argument("--issuer", required=True)
        command.add_argument("--key-file", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def load(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    now = int(time.time() * 1000)
    try:
        if args.command == "freeze":
            manifest = validate_manifest(load(args.spec))
            require(
                0 <= now - manifest["frozenAtEpochMs"] <= 5000, "CANNOT_BACKDATE_MANIFEST_FREEZE"
            )
            result = seal(
                "manifest",
                manifest,
                issuer=args.issuer,
                key=args.key_file.read_bytes(),
                manifest_digest=digest(manifest),
                subject_value=manifest["subject"],
            )
        elif args.command == "finalize":
            result = finalize(
                load(args.manifest),
                load(args.receipts),
                load(args.current_context),
                load(args.trusted_keys),
                now_ms=now,
                issuer=args.issuer,
                key=args.key_file.read_bytes(),
            )
        else:
            result = validate_finalized(
                load(args.input),
                load(args.manifest),
                load(args.receipts),
                load(args.current_context),
                load(args.trusted_keys),
                now_ms=now,
            )
            print(json.dumps(result, sort_keys=True))
            raise SystemExit(0 if result["combinedTargetResult"] == "SUCCESS" else 2)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".tmp")
        temporary.write_bytes(canonical(result) + b"\n")
        temporary.replace(args.output)
        if args.command == "finalize":
            disposition = result["payload"]["result"]["combinedTargetResult"]
            print(disposition)
            raise SystemExit(0 if disposition == "SUCCESS" else 2)
    except (ValueError, TypeError, KeyError, OSError):
        parser.exit(2, "v3 protocol input, authority, or current evidence is invalid\n")


if __name__ == "__main__":
    main()
