#!/usr/bin/env python3
"""Validate exact run-bound always-run production postflight evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FIELDS = {
    "schemaVersion",
    "runId",
    "workflowSha",
    "planDigest",
    "observedAt",
    "expectedSha",
    "deployedSha",
    "runtimeManifestDigest",
    "schemaRevision",
    "databaseEngine",
    "services",
    "releaseExact",
    "servicesExact",
    "serviceCount",
    "hostReady",
    "endpointsHealthy",
    "watchdogExpected",
    "watchdogActive",
    "finalCapacity",
    "annotationsEnabled",
    "monthToDateCost",
    "currency",
    "aggregateOnly",
}


def validate(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("postflight evidence fields are invalid")
    if value["schemaVersion"] != 1 or value["currency"] != "SGD" or value["monthToDateCost"] != 0:
        raise ValueError("postflight cost evidence failed")
    if value["finalCapacity"] != 300 or value["annotationsEnabled"] is not False:
        raise ValueError("postflight safety floor is invalid")
    if not all(
        value[name] is True
        for name in (
            "releaseExact",
            "servicesExact",
            "hostReady",
            "endpointsHealthy",
            "aggregateOnly",
            "watchdogExpected",
            "watchdogActive",
        )
    ):
        raise ValueError("postflight runtime evidence failed")
    services = value["services"]
    core = {"api", "caddy", "classroom", "tile-service", "tusd", "worker"}
    if (
        not isinstance(services, list)
        or services != sorted(set(services))
        or not core.issubset(services)
        or value["serviceCount"] != len(services)
        or value["databaseEngine"] not in {"sqlite", "postgres"}
        or (value["databaseEngine"] == "postgres") != ("postgres" in services)
    ):
        raise ValueError("postflight runtime topology is invalid")
    if value["expectedSha"] != value["deployedSha"]:
        raise ValueError("postflight release mismatch")
    if (
        re.fullmatch(r"[0-9a-f]{40}", str(value["workflowSha"])) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(value["planDigest"])) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(value["runtimeManifestDigest"])) is None
        or re.fullmatch(r"[0-9A-Za-z_]{1,128}", str(value["schemaRevision"])) is None
    ):
        raise ValueError("postflight binding is invalid")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    validate(json.loads(args.path.read_text()))


if __name__ == "__main__":
    main()
