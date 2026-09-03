from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SECURITY_DIR = ROOT / "docs" / "security"
ASVS_PATH = SECURITY_DIR / "asvs-5.0.0-l2-map.json"
SURFACE_PATH = SECURITY_DIR / "security-surface.json"
EGRESS_PATH = SECURITY_DIR / "egress-inventory.json"
FINDINGS_PATH = SECURITY_DIR / "security-findings.json"

EXPECTED_CHAPTER_COUNTS = {
    "V1": 27,
    "V2": 11,
    "V3": 19,
    "V4": 10,
    "V5": 9,
    "V6": 35,
    "V7": 18,
    "V8": 7,
    "V9": 7,
    "V10": 29,
    "V11": 14,
    "V12": 9,
    "V13": 13,
    "V14": 9,
    "V15": 13,
    "V16": 16,
    "V17": 7,
}
EXPECTED_EXCLUSIONS = {"SECRET", "PHI_PRIVATE_PIXEL", "ASSESSMENT_ANSWER", "TELEMETRY"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
EGRESS_RE = re.compile(
    r"https?://|urllib\.request|requests\.|httpx\.|\bcurl\b|\bwget\b|"
    r"\bgh\s+(?:api|run|pr)\b|\boci\b|\bssh\b|\bscp\b|"
    r"\bgit\s+(?:fetch|clone|pull)\b|\b(?:pip|pnpm|npm)\s+install\b|"
    r"\bdocker\s+(?:build|pull)\b|socket\.create_connection",
    re.IGNORECASE,
)


def _literal_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def discover_backend_routes(root: Path = ROOT) -> list[str]:
    routes: set[str] = set()
    for source in sorted((root / "server" / "wsi_viewer").glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        relative = source.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call) or not isinstance(
                        decorator.func, ast.Attribute
                    ):
                        continue
                    method = decorator.func.attr.lower()
                    if method not in HTTP_METHODS or not decorator.args:
                        continue
                    path = _literal_string(decorator.args[0])
                    if path:
                        routes.add(f"{method.upper()}|{path}|{relative}|{node.name}")
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "add_api_route" or len(node.args) < 2:
                continue
            path = _literal_string(node.args[0])
            endpoint = node.args[1].id if isinstance(node.args[1], ast.Name) else None
            methods = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "methods"), None
            )
            if not path or not endpoint or not isinstance(methods, (ast.List, ast.Tuple)):
                raise ValueError(f"non-literal add_api_route contract in {relative}:{node.lineno}")
            for method_node in methods.elts:
                method = _literal_string(method_node)
                if not method:
                    raise ValueError(f"non-literal route method in {relative}:{node.lineno}")
                routes.add(f"{method.upper()}|{path}|{relative}|{endpoint}")
    return sorted(routes)


def discover_frontend_routes(root: Path = ROOT) -> list[str]:
    source = (root / "apps" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'<Route\s+path="([^"]+)"', source)))


def set_digest(values: list[str]) -> str:
    payload = "".join(f"{value}\n" for value in values).encode()
    return hashlib.sha256(payload).hexdigest()


def _matches_route(path: str, rule: dict[str, Any]) -> bool:
    return path == rule["value"] if rule["kind"] == "exact" else path.startswith(rule["value"])


def reconcile_routes(routes: list[str], rules: list[dict[str, Any]]) -> None:
    for route in routes:
        path = route.split("|", 3)[1]
        match = next((rule for rule in rules if _matches_route(path, rule)), None)
        if match is None:
            raise ValueError(f"backend route is unmapped: {route}")


def reconcile_frontend(routes: list[str], rules: list[dict[str, Any]]) -> None:
    for route in routes:
        match = next(
            (
                rule
                for rule in rules
                if route.startswith(rule["pathPrefix"]) or rule["pathPrefix"] == "*"
            ),
            None,
        )
        if match is None:
            raise ValueError(f"frontend route is unmapped: {route}")


def discover_egress_files(root: Path, discovery_roots: list[str]) -> list[str]:
    discovered: set[str] = set()
    for relative_root in discovery_roots:
        base = root / relative_root
        for path in sorted(base.rglob("*")):
            if not path.is_file() or any(
                part in {"node_modules", "dist", "__pycache__"} for part in path.parts
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if EGRESS_RE.search(text):
                discovered.add(path.relative_to(root).as_posix())
    return sorted(discovered)


def reconcile_egress(
    paths: list[str], rules: list[dict[str, Any]], *, require_used_rules: bool = True
) -> None:
    used: set[str] = set()
    for path in paths:
        matches = [rule for rule in rules if fnmatch.fnmatchcase(path, rule["glob"])]
        if len(matches) != 1:
            raise ValueError(
                f"egress-bearing file must map exactly once: {path} ({len(matches)} matches)"
            )
        used.add(matches[0]["glob"])
    if require_used_rules:
        stale = sorted({rule["glob"] for rule in rules} - used)
        if stale:
            raise ValueError(f"egress rules have no discovered evidence: {', '.join(stale)}")


def evaluate_findings(findings: list[dict[str, Any]], assessed_at: str) -> str:
    assessed = datetime.fromisoformat(assessed_at.replace("Z", "+00:00"))
    if assessed.tzinfo is None:
        assessed = assessed.replace(tzinfo=UTC)
    for finding in findings:
        if not finding.get("owner") or not finding.get("ownerTasks"):
            raise ValueError(f"finding lacks owner/task: {finding.get('id', '<unknown>')}")
        severity = finding.get("severity")
        if (
            severity == "Critical"
            and finding.get("reachable", False)
            and finding.get("status") != "RESOLVED"
        ):
            return "NEGATIVE"
        if severity == "High" and finding.get("status") != "RESOLVED":
            if (
                finding.get("status") != "MITIGATED"
                or finding.get("mitigationVerified") is not True
            ):
                return "NEGATIVE"
            expiry_raw = finding.get("expiresAt")
            if not expiry_raw:
                return "NEGATIVE"
            expiry = datetime.fromisoformat(expiry_raw.replace("Z", "+00:00"))
            if expiry <= assessed or expiry > assessed + timedelta(days=30):
                return "NEGATIVE"
    return "SUCCESS"


def validate(root: Path = ROOT) -> dict[str, Any]:
    asvs = json.loads((root / ASVS_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))
    surface = json.loads((root / SURFACE_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))
    egress = json.loads((root / EGRESS_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))
    findings = json.loads((root / FINDINGS_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))

    counts = {item["chapter"]: item["controlCount"] for item in asvs["chapterMappings"]}
    if counts != EXPECTED_CHAPTER_COUNTS or sum(counts.values()) != 253:
        raise ValueError("ASVS Level 2 chapter reconciliation mismatch")
    if set(asvs["evidenceExclusions"]) != EXPECTED_EXCLUSIONS:
        raise ValueError("security evidence exclusions changed")
    for mapping in asvs["chapterMappings"]:
        if not mapping.get("owner") or not mapping.get("ownerTasks"):
            raise ValueError(f"ASVS chapter lacks owner/task: {mapping['chapter']}")
        if mapping["disposition"] == "NOT_APPLICABLE":
            if len(mapping.get("controlIds", [])) != mapping["controlCount"] or not mapping.get(
                "evidence"
            ):
                raise ValueError(f"ASVS N/A evidence mismatch: {mapping['chapter']}")
        elif not mapping.get("surfaceClasses"):
            raise ValueError(f"applicable ASVS chapter lacks surfaces: {mapping['chapter']}")

    backend = discover_backend_routes(root)
    frontend = discover_frontend_routes(root)
    if (
        len(backend) != surface["backendRouteCount"]
        or set_digest(backend) != surface["backendRouteSetSha256"]
    ):
        raise ValueError("backend route inventory is stale")
    if (
        len(frontend) != surface["frontendRouteCount"]
        or set_digest(frontend) != surface["frontendRouteSetSha256"]
    ):
        raise ValueError("frontend route inventory is stale")
    reconcile_routes(backend, surface["routeRules"])
    reconcile_frontend(frontend, surface["frontendClasses"])

    egress_paths = discover_egress_files(root, egress["discoveryRoots"])
    reconcile_egress(egress_paths, egress["rules"])
    result = evaluate_findings(findings["findings"], datetime.now(UTC).isoformat())
    return {
        "backendRoutes": len(backend),
        "frontendRoutes": len(frontend),
        "egressFiles": len(egress_paths),
        "findingResult": result,
    }


def main() -> int:
    argparse.ArgumentParser().parse_args()
    try:
        result = validate()
    except (OSError, ValueError, json.JSONDecodeError, SyntaxError) as exc:
        print(f"security baseline FAIL: {exc}")
        return 1
    print(
        "security baseline PASS: "
        f"{result['backendRoutes']} backend routes, {result['frontendRoutes']} frontend routes, "
        f"{result['egressFiles']} egress-bearing files; finding policy {result['findingResult']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
