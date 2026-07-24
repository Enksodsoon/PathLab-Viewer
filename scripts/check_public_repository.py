#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
TEXT_SUFFIXES = {
    "",
    ".caddyfile",
    ".css",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
PRIVATE_KEY_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
)
TOKEN_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
)
EMAIL_PATTERN = re.compile(r"(?<![\w.+-])([\w.+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.-])")
IPV4_PATTERN = re.compile(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")
DYNAMIC_DNS_PATTERN = re.compile(r"\b(?:[0-9]{1,3}[-.]){3}[0-9]{1,3}\.(?:sslip|nip)\.io\b", re.I)
ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.net",
    "example.org",
    "example.test",
    "users.noreply.github.com",
}
LOCK_NAMES = {"pnpm-lock.yaml", "package-lock.json", "yarn.lock"}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


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


def main() -> int:
    findings: list[tuple[str, int, str]] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if path.resolve() == SELF:
            continue
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            findings.append((relative, 1, "committed environment file"))
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
            "Caddyfile",
            "Dockerfile",
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(marker in line for marker in PRIVATE_KEY_MARKERS):
                findings.append((relative, line_number, "private key material"))
            if any(pattern.search(line) for pattern in TOKEN_PATTERNS):
                findings.append((relative, line_number, "credential-like token"))
            if DYNAMIC_DNS_PATTERN.search(line):
                findings.append((relative, line_number, "IP-derived public hostname"))
            for _, domain in EMAIL_PATTERN.findall(line):
                if domain.casefold() not in ALLOWED_EMAIL_DOMAINS:
                    findings.append((relative, line_number, "non-example email address"))
            if path.name not in LOCK_NAMES:
                for candidate in IPV4_PATTERN.findall(line):
                    if is_public_ip(candidate):
                        findings.append((relative, line_number, "public IP address"))
    if findings:
        for path, line, category in sorted(set(findings)):
            print(f"{path}:{line}: {category}", file=sys.stderr)
        print("Public repository check failed.", file=sys.stderr)
        return 1
    print("Public repository check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
