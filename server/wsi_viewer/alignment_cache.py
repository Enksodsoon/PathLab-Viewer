"""Opt-in serial benchmark reset of unbound immutable regional tile caches."""

from __future__ import annotations

import os
import stat
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .alignment_inputs import immutable_descriptor


def _is_reparse(path: Path) -> bool:
    value = path.lstat()
    return stat.S_ISLNK(value.st_mode) or bool(getattr(value, "st_file_attributes", 0) & 0x400)


def _regular_ancestors(path: Path) -> None:
    for ancestor in (path, *path.parents):
        if _is_reparse(ancestor):
            raise ValueError("immutable cache reset refuses symlink/reparse ancestors")


def reset_generated_regional_cache(roots: list[Path], workspace: Path) -> dict[str, Any]:
    """Call only between terminal contained children; never reset bound copied tiles."""
    started = time.monotonic()
    workspace = workspace.absolute()
    if not workspace.is_dir():
        raise ValueError("immutable cache workspace is unavailable")
    _regular_ancestors(workspace)
    workspace = workspace.resolve()
    candidates: list[tuple[Path, int]] = []
    verified: list[Path] = []
    kinds: Counter[str] = Counter()
    seen = set()
    for root in roots:
        root = root.absolute()
        if not root.resolve().is_relative_to(workspace):
            raise ValueError("immutable cache source escapes input workspace")
        _regular_ancestors(root)
        root = root.resolve()
        if root in seen:
            continue
        seen.add(root)
        descriptor = immutable_descriptor(root)
        region = descriptor["regionSource"]
        kind = region.get("kind")
        kinds[
            kind
            if kind
            in {
                "openslide-original",
                "verified-openslide-candidate",
                "copied-dzi",
                "copied-dzi-incomplete",
            }
            else "unavailable"
        ] += 1
        verified.append(root)
        if region.get("kind") not in {"openslide-original", "verified-openslide-candidate"}:
            continue
        cache = root / "slide_files"
        protected = [
            descriptor["image"],
            "slide.dzi",
            "immutable-overview.json",
            ".openslide-source.json",
            region["file"],
        ]
        protected.extend([region[key] for key in ("admissionFile",) if key in region])
        original = descriptor.get("originalSource", {})
        if isinstance(original, dict) and original.get("copiedBytesVerified") is True:
            protected.append(original["file"])
        if any((root / name).resolve().is_relative_to(cache) for name in protected):
            raise ValueError("immutable cache overlaps a bound input file")
        if not cache.exists():
            continue
        pending = [cache]
        while pending:
            directory = pending.pop()
            _regular_ancestors(directory)
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if _is_reparse(path) or not path.resolve().is_relative_to(cache):
                        raise ValueError("immutable cache reset refuses escaped/reparse entries")
                    info = path.stat()
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(path)
                    elif stat.S_ISREG(info.st_mode):
                        candidates.append((path.resolve(), info.st_size))
                    else:
                        raise ValueError("immutable cache reset requires regular files")
                    if len(candidates) + len(pending) > 100_000:
                        raise ValueError("immutable generated cache inventory exceeds bound")
    # Validate the entire inventory before the first mutation. No recursive delete.
    for path, size in candidates:
        _regular_ancestors(path)
        if not path.is_file() or path.stat().st_size != size:
            raise ValueError("immutable generated cache changed before reset")
        path.unlink()
    for root in verified:
        immutable_descriptor(root)
    return {
        "policy": "process-cold-generated-regional-cache-empty/1",
        "performed": True,
        "wallSeconds": time.monotonic() - started,
        "removedFileCount": len(candidates),
        "removedBytes": sum(size for _, size in candidates),
        "sourceKindCounts": dict(kinds),
        "hostFilesystemCacheState": "unmeasured",
    }
