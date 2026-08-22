#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_RELATIVE = Path(__file__).resolve().relative_to(ROOT).as_posix()
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
EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])([\w.+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.-])"
)
IPV4_PATTERN = re.compile(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")
DYNAMIC_DNS_PATTERN = re.compile(
    r"\b(?:[0-9]{1,3}[-.]){3}[0-9]{1,3}\.(?:sslip|nip)\.io\b", re.I
)
LOCAL_PATH_PATTERNS = (
    re.compile(r"\b[A-Za-z]:\\+Users\\+[^\\\s]+\\+", re.I),
    re.compile(r"(?<![\w/])/Users/[^/\s]+/"),
    re.compile(r"(?<![\w/])/home/(?!runner(?:/|$))[^/\s]+/"),
)
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
        if path.name not in LOCK_NAMES:
            for candidate in IPV4_PATTERN.findall(line):
                if is_public_ip(candidate):
                    findings.append((display, line_number, "public IP address"))
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
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
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
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


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
            try:
                blob = git("rev-parse", f"{commit}:{relative}").stdout.decode().strip()
            except subprocess.CalledProcessError:
                continue
            key = (blob, relative)
            if key in seen_blobs:
                continue
            seen_blobs.add(key)
            text = text_at_commit(commit, relative)
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
