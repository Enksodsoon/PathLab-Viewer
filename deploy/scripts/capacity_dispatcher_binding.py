#!/usr/bin/env python3
"""Validate the stable capacity controller binding without requiring exec bits."""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path
from typing import Protocol

CONTROLLER_PATTERN = re.compile(r"^/run/pathlab-capacity-[a-z0-9-]{1,64}-controller$")
CONTROLLER_SCRIPT = "capacity-control-host.sh"
MAX_POINTER_BYTES = 128


class StatLike(Protocol):
    @property
    def st_mode(self) -> int: ...

    @property
    def st_uid(self) -> int: ...


class BindingError(ValueError):
    """The stable binding is not safe to dispatch."""


def _require_pointer(pointer: StatLike, *, expected_uid: int) -> None:
    if not stat.S_ISREG(pointer.st_mode) or pointer.st_uid != expected_uid:
        raise BindingError("controller pointer is not an owned regular file")
    if stat.S_IMODE(pointer.st_mode) != 0o600:
        raise BindingError("controller pointer permissions are not private")


def _require_directory(directory: StatLike, *, expected_uid: int) -> None:
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != expected_uid:
        raise BindingError("controller directory is not an owned directory")
    if stat.S_IMODE(directory.st_mode) != 0o700:
        raise BindingError("controller directory permissions are not private")


def _require_script(script: StatLike, *, expected_uid: int) -> None:
    if not stat.S_ISREG(script.st_mode) or script.st_uid != expected_uid:
        raise BindingError("controller script is not an owned regular file")
    script_mode = stat.S_IMODE(script.st_mode)
    if script_mode & stat.S_IRUSR == 0 or script_mode & 0o022:
        raise BindingError("controller script is not trusted and owner-readable")


def validate_binding_metadata(
    pointer_text: str,
    *,
    pointer: StatLike,
    directory: StatLike,
    script: StatLike,
    expected_uid: int = 0,
) -> Path:
    if not pointer_text.endswith("\n") or pointer_text.count("\n") != 1:
        raise BindingError("controller pointer framing is invalid")
    controller_text = pointer_text.removesuffix("\n")
    if CONTROLLER_PATTERN.fullmatch(controller_text) is None:
        raise BindingError("controller path is invalid")
    _require_pointer(pointer, expected_uid=expected_uid)
    _require_directory(directory, expected_uid=expected_uid)
    _require_script(script, expected_uid=expected_uid)
    return Path(controller_text) / CONTROLLER_SCRIPT


def _open_readonly_nofollow(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    return os.open(path, flags)


def resolve_binding(pointer_path: Path, *, expected_uid: int = 0) -> Path:
    pointer_lstat = pointer_path.lstat()
    _require_pointer(pointer_lstat, expected_uid=expected_uid)
    descriptor = _open_readonly_nofollow(pointer_path)
    try:
        pointer_fstat = os.fstat(descriptor)
        if (
            pointer_fstat.st_dev != pointer_lstat.st_dev
            or pointer_fstat.st_ino != pointer_lstat.st_ino
        ):
            raise BindingError("controller pointer changed during validation")
        raw_pointer = os.read(descriptor, MAX_POINTER_BYTES + 1)
        if len(raw_pointer) > MAX_POINTER_BYTES:
            raise BindingError("controller pointer is too long")
        try:
            pointer_text = raw_pointer.decode("ascii")
        except UnicodeDecodeError as exc:
            raise BindingError("controller pointer is not ASCII") from exc
    finally:
        os.close(descriptor)

    controller_text = pointer_text.removesuffix("\n")
    if CONTROLLER_PATTERN.fullmatch(controller_text) is None:
        raise BindingError("controller path is invalid")
    directory_path = Path(controller_text)
    directory_lstat = directory_path.lstat()
    _require_directory(directory_lstat, expected_uid=expected_uid)
    script_path = directory_path / CONTROLLER_SCRIPT
    script_lstat = script_path.lstat()
    _require_script(script_lstat, expected_uid=expected_uid)
    script_descriptor = _open_readonly_nofollow(script_path)
    try:
        script_fstat = os.fstat(script_descriptor)
        if script_fstat.st_dev != script_lstat.st_dev or script_fstat.st_ino != script_lstat.st_ino:
            raise BindingError("controller script changed during validation")
        os.read(script_descriptor, 1)
    finally:
        os.close(script_descriptor)

    return validate_binding_metadata(
        pointer_text,
        pointer=pointer_fstat,
        directory=directory_lstat,
        script=script_fstat,
        expected_uid=expected_uid,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pointer", type=Path)
    args = parser.parse_args()
    try:
        script = resolve_binding(args.pointer, expected_uid=0)
    except (BindingError, OSError) as exc:
        print(f"capacity controller binding rejected: {exc}", file=sys.stderr)
        return 1
    print(script)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
