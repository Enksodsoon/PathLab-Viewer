#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import re
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
SKIP_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".terraform",
    ".venv",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "playwright-report",
    "test-results",
    "var",
}
BINARY_SUFFIXES = {
    ".avif",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".svgz",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}
PRIVATE_DATA_SUFFIXES = {
    ".db",
    ".dzi",
    ".ndpi",
    ".mrxs",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
    ".svs",
    ".tif",
    ".tiff",
    ".vsi",
}
PRIVATE_FILENAMES = {
    ".env",
    "AGENTS.md",
    "CLAUDE.md",
    "id_ed25519",
    "id_rsa",
    "PROMPT.md",
}
ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.test",
    "users.noreply.github.com",
}
ALLOWED_HOME_USERS = {
    "example",
    "pathlab",
    "runner",
    "ubuntu",
    "user",
}
ALLOWED_DUCKDNS_HOSTS = {
    "www.duckdns.org",
    "your-subdomain.duckdns.org",
}
MAX_TEXT_BYTES = 10 * 1024 * 1024

EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])([\w.+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,}))(?![\w.-])"
)
IPV4_PATTERN = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
HOME_PATTERN = re.compile(
    r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)([^/\\\s'\"]+)"
)
DYNAMIC_HOST_PATTERN = re.compile(
    r"(?i)\b(?:[A-Za-z0-9-]+\.)+"
    r"(?:sslip\.io|nip\.io|ngrok\.io|trycloudflare\.com|localhost\.run)\b"
)
DUCKDNS_HOST_PATTERN = re.compile(r"(?i)\b([A-Za-z0-9-]+\.duckdns\.org)\b")
GENERIC_SECRET_PATTERN = re.compile(
    r"(?i)\b(?:password|secret|token|api[_-]?key)\b"
    r"\s*[:=]\s*(['\"])([A-Za-z0-9+/=_-]{16,})\1"
)
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private key material",
        re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    ),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    (
        "GitHub fine-grained token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("OpenAI-style token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
)
INTERNAL_ARTIFACT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "agent execution instruction",
        re.compile(r"For " + r"agentic workers", re.IGNORECASE),
    ),
    (
        "agent workflow artifact",
        re.compile(r"subagent" + r"-driven-development", re.IGNORECASE),
    ),
    (
        "internal planning directory",
        re.compile(r"docs/" + r"superpowers", re.IGNORECASE),
    ),
    (
        "internal automation branch convention",
        re.compile(r"\bcodex/", re.IGNORECASE),
    ),
)


def is_example_secret(value: str) -> bool:
    lowered = value.casefold()
    return any(
        marker in lowered
        for marker in (
            "example",
            "placeholder",
            "replace",
            "generate",
            "ci-only",
            "not-used",
        )
    )


def report(
    findings: list[str],
    path: Path,
    reason: str,
    line_number: int | None = None,
) -> None:
    relative = path.relative_to(ROOT).as_posix()
    location = f"{relative}:{line_number}" if line_number is not None else relative
    findings.append(f"{location}: {reason}")


def iter_repository_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRECTORIES for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file() or path.is_symlink():
            files.append(path)
    return sorted(files)


def check_path(path: Path, findings: list[str]) -> bool:
    relative = PurePosixPath(path.relative_to(ROOT).as_posix())
    if path.is_symlink():
        report(findings, path, "symbolic links are not allowed in the public repository")
        return False
    if relative.name in PRIVATE_FILENAMES and relative.name != ".env.example":
        report(findings, path, "private or internal-purpose filename is not allowed")
    if relative.suffix.casefold() in PRIVATE_DATA_SUFFIXES:
        report(
            findings,
            path,
            "private data, credential, database, or generated-slide file is not allowed",
        )
    if relative.name.endswith(".prompt.md"):
        report(findings, path, "prompt artifact filename is not allowed")
    return relative.suffix.casefold() not in BINARY_SUFFIXES


def check_text(path: Path, text: str, findings: list[str]) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        for reason, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                report(findings, path, reason, line_number)
        generic_secret = GENERIC_SECRET_PATTERN.search(line)
        if generic_secret and not is_example_secret(generic_secret.group(2)):
            report(findings, path, "possible committed credential", line_number)
        for _, domain in EMAIL_PATTERN.findall(line):
            if domain.casefold() not in ALLOWED_EMAIL_DOMAINS:
                report(findings, path, "non-example email address", line_number)
        for candidate in IPV4_PATTERN.findall(line):
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if address.version == 4 and address.is_global:
                report(findings, path, "public IPv4 address", line_number)
        if DYNAMIC_HOST_PATTERN.search(line):
            report(findings, path, "temporary or IP-derived public hostname", line_number)
        for hostname in DUCKDNS_HOST_PATTERN.findall(line):
            if hostname.casefold() not in ALLOWED_DUCKDNS_HOSTS:
                report(findings, path, "traceable DuckDNS hostname", line_number)
        for username in HOME_PATTERN.findall(line):
            allowed_user = username.casefold() in ALLOWED_HOME_USERS
            if not allowed_user and not username.startswith("${"):
                report(findings, path, "personal workstation path", line_number)
        for reason, pattern in INTERNAL_ARTIFACT_PATTERNS:
            if pattern.search(line):
                report(findings, path, reason, line_number)


def main() -> int:
    findings: list[str] = []
    scanned = 0
    for path in iter_repository_files():
        should_scan_text = check_path(path, findings)
        if not should_scan_text or path.resolve() == SELF:
            continue
        size = path.stat().st_size
        if size > MAX_TEXT_BYTES:
            report(
                findings,
                path,
                "large unreviewed file exceeds the public-text scan limit",
            )
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            report(findings, path, "non-UTF-8 file requires explicit public review")
            continue
        scanned += 1
        check_text(path, text, findings)

    if findings:
        finding_count = len(set(findings))
        print(
            "Public repository guard found "
            f"{finding_count} finding(s); sensitive details suppressed.",
            file=sys.stderr,
        )
        return 1
    print(f"Public repository guard passed ({scanned} text files scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
