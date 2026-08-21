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
    if value["finalCapacity"] not in (300, 1200, 1500):
        raise ValueError("postflight capacity is invalid")
    if value["annotationsEnabled"] is not (value["finalCapacity"] in (1200, 1500)):
        raise ValueError("postflight annotation activation is inconsistent")
    if not all(
        value[name] is True
        for name in (
            "releaseExact",
            "servicesExact",
            "hostReady",
            "endpointsHealthy",
            "aggregateOnly",
        )
    ):
        raise ValueError("postflight runtime evidence failed")
    if value["serviceCount"] not in (5, 6):
        raise ValueError("postflight service count is invalid")
    if value["watchdogActive"] is not value["watchdogExpected"]:
        raise ValueError("postflight watchdog state does not match the expected release")
    if value["expectedSha"] != value["deployedSha"]:
        raise ValueError("postflight release mismatch")
    if (
        re.fullmatch(r"[0-9a-f]{40}", str(value["workflowSha"])) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(value["planDigest"])) is None
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
