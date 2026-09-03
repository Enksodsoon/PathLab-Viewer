#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_RELATIVE = Path(__file__).resolve().relative_to(ROOT).as_posix()
TEXT_SUFFIXES = {
    "",
    ".bat",
    ".caddyfile",
    ".cfg",
    ".cmd",
    ".cnf",
    ".conf",
    ".config",
    ".css",
    ".csv",
    ".env",
    ".hcl",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".p12",
    ".path",
    ".pem",
    ".pfx",
    ".key",
    ".properties",
    ".ps1",
    ".py",
    ".service",
    ".sh",
    ".socket",
    ".sql",
    ".target",
    ".tf",
    ".timer",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
PRIVATE_KEY_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
    "-----BEGIN DSA PRIVATE KEY-----",
    "-----BEGIN ENCRYPTED PRIVATE KEY-----",
    "-----BEGIN PGP PRIVATE KEY BLOCK-----",
)
TOKEN_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
)
EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])([\w.+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.-])"
)
IPV4_PATTERN = re.compile(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")
IPV6_PATTERN = re.compile(
    r"(?<![0-9A-Fa-f:.])\[?([0-9A-Fa-f:.]*:[0-9A-Fa-f:.]+)\]?"
    r"(?![0-9A-Fa-f:.])"
)
DYNAMIC_DNS_PATTERN = re.compile(
    r"\b(?:[0-9]{1,3}[-.]){3}[0-9]{1,3}\.(?:sslip|nip)\.io\b", re.I
)
LOCAL_PATH_PATTERNS = (
    re.compile(r"\b[A-Za-z]:\\+Users\\+[^\\\s]+\\+", re.I),
    re.compile(r"(?<![\w/])/Users/[^/\s]+/"),
    re.compile(r"(?<![\w/])/home/(?!runner(?:/|$))[^/\s]+/"),
    re.compile(
        r"(?<![\\\w])\\\\[A-Za-z0-9][A-Za-z0-9._-]{0,252}"
        r"\\[A-Za-z0-9$][A-Za-z0-9$._ -]{0,79}"
        r"(?=\\|[\s'\"),;]|$)",
        re.I,
    ),
)
BINARY_SECRET_SUFFIXES = {".p12", ".pfx"}
SENSITIVE_PATH_PARTS = {".claude", ".codex", ".cursor", ".superpowers"}
ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.net",
    "example.org",
    "example.test",
    "users.noreply.github.com",
}
ALLOWED_EXACT_EMAILS = {"noreply@github.com"}
ALLOWED_RESERVED_EMAIL_SUFFIXES = (".example", ".invalid", ".test")
LOCK_NAMES = {"pnpm-lock.yaml", "package-lock.json", "yarn.lock"}

Finding = tuple[str, int, str]

REQUIRED_RIGHTS_FILES = (
    "LICENSE",
    "NOTICE",
    "docs/supply-chain/LICENSE_AND_NOTICE_POLICY.md",
)


def _read_required_text(root: Path, relative: str) -> tuple[str | None, list[Finding]]:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8"), []
    except FileNotFoundError:
        return None, [(relative, 1, "required license or notice file is missing")]
    except (UnicodeDecodeError, OSError):
        return None, [(relative, 1, "required license or notice file is unreadable")]


def scan_license_policy(root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    texts: dict[str, str] = {}
    for relative in REQUIRED_RIGHTS_FILES:
        text, errors = _read_required_text(root, relative)
        findings.extend(errors)
        if text is not None:
            texts[relative] = text

    license_text = texts.get("LICENSE", "")
    if "Apache License" not in license_text or "Version 2.0, January 2004" not in license_text:
        findings.append(("LICENSE", 1, "root license is not Apache-2.0 text"))

    notice_text = texts.get("NOTICE", "")
    for marker in ("PathLab Viewer", "Copyright", "Third-party"):
        if marker not in notice_text:
            findings.append(("NOTICE", 1, f"required notice marker is missing: {marker}"))

    policy_text = texts.get("docs/supply-chain/LICENSE_AND_NOTICE_POLICY.md", "")
    for marker in (
        "SPDX-License-Identifier: Apache-2.0",
        "Signed-off-by:",
        ".dist-info/licenses/",
        "apps/web/dist",
    ):
        if marker not in policy_text:
            findings.append(
                (
                    "docs/supply-chain/LICENSE_AND_NOTICE_POLICY.md",
                    1,
                    f"required license policy marker is missing: {marker}",
                )
            )

    contributing, errors = _read_required_text(root, "CONTRIBUTING.md")
    findings.extend(errors)
    if contributing is not None:
        for marker in ("Signed-off-by:", "Developer Certificate of Origin", "tool-assisted"):
            if marker not in contributing:
                findings.append(
                    ("CONTRIBUTING.md", 1, f"contribution provenance rule is missing: {marker}")
                )

    pyproject_text, errors = _read_required_text(root, "pyproject.toml")
    findings.extend(errors)
    if pyproject_text is not None:
        try:
            project = tomllib.loads(pyproject_text).get("project", {})
        except tomllib.TOMLDecodeError:
            findings.append(("pyproject.toml", 1, "package metadata is invalid TOML"))
        else:
            if project.get("license") != "Apache-2.0":
                findings.append(("pyproject.toml", 1, "Python package license is not Apache-2.0"))
            if set(project.get("license-files", [])) != {"LICENSE", "NOTICE"}:
                findings.append(
                    ("pyproject.toml", 1, "Python package license-files must be LICENSE and NOTICE")
                )

    for relative in ("package.json", "apps/web/package.json"):
        package_text, errors = _read_required_text(root, relative)
        findings.extend(errors)
        if package_text is None:
            continue
        try:
            package = json.loads(package_text)
        except json.JSONDecodeError:
            findings.append((relative, 1, "package metadata is invalid JSON"))
            continue
        if package.get("license") != "Apache-2.0":
            findings.append((relative, 1, "JavaScript package license is not Apache-2.0"))

    web_package_path = root / "apps/web/package.json"
    if web_package_path.is_file():
        try:
            web_package = json.loads(web_package_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
        else:
            build = web_package.get("scripts", {}).get("build", "")
            if "copy-release-legal-files.mjs" not in build:
                findings.append(
                    ("apps/web/package.json", 1, "web build does not copy release legal files")
                )
    if not (root / "apps/web/scripts/copy-release-legal-files.mjs").is_file():
        findings.append(
            (
                "apps/web/scripts/copy-release-legal-files.mjs",
                1,
                "web release legal-file copier is missing",
            )
        )

    return findings


def git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def tracked_files() -> list[Path]:
    result = git("ls-files", "-z")
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def is_allowed_email(value: str) -> bool:
    normalized = value.casefold()
    if normalized in ALLOWED_EXACT_EMAILS:
        return True
    local_part, separator, domain = normalized.rpartition("@")
    return bool(
        separator
        and local_part
        and "@" not in local_part
        and (
            domain in ALLOWED_EMAIL_DOMAINS
            or domain.endswith(ALLOWED_RESERVED_EMAIL_SUFFIXES)
        )
    )


def is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def is_embedded_numeric_identifier(line: str, start: int, end: int) -> bool:
    """Return true when an IPv4-shaped substring is one segment of a longer OID."""
    has_numeric_segment_before = (
        start >= 2 and line[start - 1] == "." and line[start - 2].isdigit()
    )
    has_numeric_segment_after = (
        end + 1 < len(line) and line[end] == "." and line[end + 1].isdigit()
    )
    return has_numeric_segment_before or has_numeric_segment_after


def is_lockfile_network_context(line: str, start: int) -> bool:
    prefix = line[max(0, start - 160) : start]
    return bool(
        re.search(
            r"(?:https?|ssh|git)://[^\s'\"<>]*$|"
            r"(?:host|hostname|address|endpoint|resolved|url)\s*[:=]\s*[^\s'\"<>]*$",
            prefix,
            re.IGNORECASE,
        )
    )


def is_sensitive_repository_path(relative: str) -> bool:
    return any(part.casefold() in SENSITIVE_PATH_PARTS for part in Path(relative).parts)


def should_scan_text(relative: str) -> bool:
    path = Path(relative)
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {"Caddyfile", "Dockerfile"}


def scan_text(relative: str, text: str, *, label: str | None = None) -> list[Finding]:
    findings: list[Finding] = []
    display = f"{label}:{relative}" if label else relative
    path = Path(relative)

    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        findings.append((display, 1, "committed environment file"))
        return findings

    if not should_scan_text(relative):
        return findings

    if path.suffix.casefold() in BINARY_SECRET_SUFFIXES:
        findings.append((display, 1, "sensitive credential container"))
        return findings

    for line_number, line in enumerate(text.splitlines(), start=1):
        if any(marker in line for marker in PRIVATE_KEY_MARKERS):
            findings.append((display, line_number, "private key material"))
        if any(pattern.search(line) for pattern in TOKEN_PATTERNS):
            findings.append((display, line_number, "credential-like token"))
        if DYNAMIC_DNS_PATTERN.search(line):
            findings.append((display, line_number, "IP-derived public hostname"))
        if any(pattern.search(line) for pattern in LOCAL_PATH_PATTERNS):
            findings.append((display, line_number, "local workstation path"))
        for local_part, domain in EMAIL_PATTERN.findall(line):
            email = f"{local_part}@{domain}"
            if not is_allowed_email(email):
                findings.append((display, line_number, "non-example email address"))
        for match in IPV4_PATTERN.finditer(line):
            if is_embedded_numeric_identifier(line, match.start(), match.end()):
                continue
            candidate = match.group(0)
            if is_public_ip(candidate) and (
                path.name not in LOCK_NAMES
                or is_lockfile_network_context(line, match.start())
            ):
                findings.append((display, line_number, "public IP address"))
        for match in IPV6_PATTERN.finditer(line):
            candidate = match.group(1)
            if is_public_ip(candidate) and (
                path.name not in LOCK_NAMES
                or is_lockfile_network_context(line, match.start())
            ):
                findings.append((display, line_number, "public IPv6 address"))
    return findings


def scan_current_tree() -> list[Finding]:
    findings: list[Finding] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative == SELF_RELATIVE:
            continue
        if is_sensitive_repository_path(relative):
            findings.append((relative, 1, "local development workspace path"))
            continue
        is_env_file = path.name == ".env" or (
            path.name.startswith(".env.") and path.name != ".env.example"
        )
        if not should_scan_text(relative) and not is_env_file:
            continue
        if is_env_file:
            findings.append((relative, 1, "committed environment file"))
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            findings.append((relative, 1, "unreadable or non-UTF-8 governed text"))
            continue
        findings.extend(scan_text(relative, text))
    return findings


def commits_after(base: str) -> list[str]:
    git("cat-file", "-e", f"{base}^{{commit}}")
    result = git("rev-list", "--reverse", f"{base}..HEAD")
    return [line.decode().strip() for line in result.stdout.splitlines() if line.strip()]


def changed_paths(commit: str) -> list[str]:
    result = git(
        "diff-tree",
        "--root",
        "--no-commit-id",
        "-r",
        "--diff-filter=ACMR",
        "--name-only",
        "-z",
        commit,
    )
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def commit_emails(commit: str) -> tuple[str, str]:
    result = git("show", "-s", "--format=%ae%x00%ce", commit)
    author, committer = result.stdout.decode().strip().split("\0", 1)
    return author, committer


def text_at_commit(commit: str, relative: str) -> str | None:
    try:
        result = git("show", f"{commit}:{relative}")
    except subprocess.CalledProcessError:
        return None
    return result.stdout.decode("utf-8")


def scan_history(base: str) -> list[Finding]:
    findings: list[Finding] = []
    seen_blobs: set[tuple[str, str]] = set()

    for commit in commits_after(base):
        short = commit[:12]
        author_email, committer_email = commit_emails(commit)
        if not is_allowed_email(author_email):
            findings.append((short, 1, "commit author email is not privacy-safe"))
        if not is_allowed_email(committer_email):
            findings.append((short, 1, "commit committer email is not privacy-safe"))

        for relative in changed_paths(commit):
            if relative == SELF_RELATIVE:
                continue
            if is_sensitive_repository_path(relative):
                findings.append((f"{short}:{relative}", 1, "local development workspace path"))
                continue
            path = Path(relative)
            is_env_file = path.name == ".env" or (
                path.name.startswith(".env.") and path.name != ".env.example"
            )
            if is_env_file:
                findings.append((f"{short}:{relative}", 1, "committed environment file"))
                continue
            if not should_scan_text(relative):
                continue
            try:
                blob = git("rev-parse", f"{commit}:{relative}").stdout.decode().strip()
            except subprocess.CalledProcessError:
                continue
            key = (blob, relative)
            if key in seen_blobs:
                continue
            seen_blobs.add(key)
            try:
                text = text_at_commit(commit, relative)
            except UnicodeDecodeError:
                findings.append(
                    (
                        f"{short}:{relative}",
                        1,
                        "unreadable or non-UTF-8 governed text",
                    )
                )
                continue
            if text is None:
                continue
            findings.extend(scan_text(relative, text, label=short))

    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reject public-repository content and newly introduced history that can "
            "disclose private data."
        )
    )
    parser.add_argument(
        "--history-base",
        help=(
            "Scan every commit and changed blob in HISTORY_BASE..HEAD in addition to "
            "the current tree."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings = scan_current_tree()
    findings.extend(scan_license_policy())
    if args.history_base:
        findings.extend(scan_history(args.history_base))

    if findings:
        for path, line, category in sorted(set(findings)):
            print(f"{path}:{line}: {category}", file=sys.stderr)
        print("Public repository check failed.", file=sys.stderr)
        return 1
    print("Public repository check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
