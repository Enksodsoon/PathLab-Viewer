"""Verify effective Caddy route order, rather than Caddyfile source order."""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
from typing import Any

PROBES = (
    "/api/v1/internal/uploads/admission",
    "/api/v1/internal/tus/hooks",
    "/_pathlab_ome/unauthorized/slide.dzi",
)


def first_response(routes: list[dict[str, Any]], path: str) -> str | None:
    for route in routes:
        matches = route.get("match", [{}])
        if not any(
            "path" not in match
            or any(fnmatch.fnmatchcase(path, pattern) for pattern in match["path"])
            for match in matches
        ):
            continue
        for handler in route.get("handle", []):
            kind = handler.get("handler")
            if kind == "subroute":
                outcome = first_response(handler.get("routes", []), path)
                if outcome is not None:
                    return outcome
            elif kind == "static_response":
                return str(handler.get("status_code", 200))
            elif kind in {"reverse_proxy", "file_server", "rewrite", "authentication"}:
                return str(kind)
    return None


def validate(document: dict[str, Any]) -> None:
    servers = document.get("apps", {}).get("http", {}).get("servers", {})
    if not servers:
        raise ValueError("Adapted configuration has no HTTP server")
    for name, server in servers.items():
        for path in PROBES:
            outcome = first_response(server.get("routes", []), path)
            if outcome != "404":
                raise ValueError(f"{name}: {path} reaches {outcome!r} before its deny response")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("adapted_json", type=Path)
    args = parser.parse_args()
    validate(json.loads(args.adapted_json.read_text(encoding="utf-8-sig")))
    print("Caddy internal-route boundaries PASS")


if __name__ == "__main__":
    main()
