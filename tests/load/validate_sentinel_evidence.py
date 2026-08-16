#!/usr/bin/env python3
"""Validate aggregate-only functional sentinel evidence."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

FEATURES = {"uploadConversion", "annotations", "libraryShare", "dynamicViewer", "desktop"}


def validate(value: object, *, require_cleanup: bool = False) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("sentinel evidence must be an object")
    allowed = {
        "schemaVersion",
        "runId",
        "workflowSha",
        "planDigest",
        "startedAt",
        "completedAt",
        "fixtureBytes",
        "adminResponsive",
        "conversionSucceeded",
        "degradedViewerRecovered",
        "functionalSentinels",
        "frontend",
        "crossBrowser",
        "cleanupSucceeded",
        "aggregateOnly",
        "syntheticOnly",
    }
    if set(value) != allowed:
        raise ValueError("sentinel evidence fields are incomplete or contain private data")
    functional = value.get("functionalSentinels")
    if not isinstance(functional, dict) or set(functional) != FEATURES:
        raise ValueError("functional sentinel evidence is incomplete")
    boolean_fields = {
        "adminResponsive",
        "conversionSucceeded",
        "degradedViewerRecovered",
        "cleanupSucceeded",
        "aggregateOnly",
        "syntheticOnly",
    }
    if any(not isinstance(value[name], bool) for name in boolean_fields):
        raise ValueError("sentinel evidence fields must be boolean")
    if any(not isinstance(item, bool) for item in functional.values()):
        raise ValueError("functional sentinel outcomes must be boolean")
    if not value["aggregateOnly"] or not value["syntheticOnly"]:
        raise ValueError("sentinel privacy boundary was not satisfied")
    if (
        not value["adminResponsive"]
        or not value["conversionSucceeded"]
        or not value["degradedViewerRecovered"]
    ):
        raise ValueError("baseline browser sentinel failed")
    if not all(functional.values()):
        raise ValueError("a functional sentinel failed")
    frontend = value.get("frontend")
    if not isinstance(frontend, dict) or set(frontend) != {
        "clsMax",
        "lcpMsMax",
        "consoleErrors",
        "networkErrors",
        "blankCanvases",
        "mobilePassed",
        "projects",
    }:
        raise ValueError("frontend SLO evidence is incomplete")
    if (
        not isinstance(frontend["clsMax"], (int, float))
        or frontend["clsMax"] > 0.1
        or not isinstance(frontend["lcpMsMax"], (int, float))
        or frontend["lcpMsMax"] <= 0
        or frontend["lcpMsMax"] > 2500
        or any(frontend[name] != 0 for name in ("consoleErrors", "networkErrors", "blankCanvases"))
        or frontend["mobilePassed"] is not True
    ):
        raise ValueError("frontend SLO evidence failed")
    projects = frontend["projects"]
    expected_projects = {"chromium", "firefox", "webkit", "mobile-chromium"}
    if not isinstance(projects, dict) or set(projects) != expected_projects:
        raise ValueError("per-browser live Classroom evidence is incomplete")
    for project, metrics in projects.items():
        if not isinstance(metrics, dict) or set(metrics) != {
            "cls",
            "lcpMs",
            "consoleErrors",
            "networkErrors",
            "blankCanvases",
            "studentInteractionsPassed",
            "teacherInteractionsPassed",
        }:
            raise ValueError(f"frontend metrics for {project} are incomplete")
        if (
            not 0 <= metrics["cls"] <= 0.1
            or not 0 < metrics["lcpMs"] <= 2500
            or any(
                metrics[name] != 0 for name in ("consoleErrors", "networkErrors", "blankCanvases")
            )
            or metrics["studentInteractionsPassed"] is not True
            or metrics["teacherInteractionsPassed"] is not True
        ):
            raise ValueError(f"frontend metrics for {project} failed")
    cross_browser = value.get("crossBrowser")
    if (
        not isinstance(cross_browser, dict)
        or set(cross_browser) != {"approved", "projects", "ciRunId"}
        or cross_browser["approved"] is not True
        or cross_browser["projects"] != ["chromium", "firefox", "webkit", "mobile-chromium"]
        or not isinstance(cross_browser["ciRunId"], int)
        or cross_browser["ciRunId"] < 1
    ):
        raise ValueError("cross-browser evidence failed")
    if require_cleanup and not value["cleanupSucceeded"]:
        raise ValueError("synthetic sentinel cleanup did not succeed")
    if value["schemaVersion"] != 1:
        raise ValueError("sentinel schema version is invalid")
    if (
        not isinstance(value["runId"], str)
        or re.fullmatch(r"[a-z0-9-]{1,64}", value["runId"]) is None
    ):
        raise ValueError("sentinel run binding is invalid")
    if (
        not isinstance(value["workflowSha"], str)
        or re.fullmatch(r"[0-9a-f]{40}", value["workflowSha"]) is None
    ):
        raise ValueError("sentinel SHA binding is invalid")
    if (
        not isinstance(value["planDigest"], str)
        or re.fullmatch(r"[0-9a-f]{64}", value["planDigest"]) is None
    ):
        raise ValueError("sentinel plan binding is invalid")
    if not isinstance(value["fixtureBytes"], int) or not (
        330_000_000 <= value["fixtureBytes"] <= 331_000_000
    ):
        raise ValueError("sentinel fixture size is invalid")
    try:
        started = datetime.fromisoformat(str(value["startedAt"]).replace("Z", "+00:00"))
        completed = datetime.fromisoformat(str(value["completedAt"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("sentinel timestamps are invalid") from error
    if started.tzinfo is None or completed.tzinfo is None or completed < started:
        raise ValueError("sentinel timestamps are invalid")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--require-cleanup", action="store_true")
    args = parser.parse_args()
    validate(
        json.loads(args.path.read_text(encoding="utf-8")), require_cleanup=args.require_cleanup
    )


if __name__ == "__main__":
    main()
