"""Explicit local admission for upstream VALIS pretrained resources."""

from __future__ import annotations

import hashlib
import importlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .alignment import AlignmentRejected

VALIS_RESOURCE_URLS = {
    "Disk": "https://raw.githubusercontent.com/cvlab-epfl/disk/master/depth-save.pth",
    "LightGlue": "https://github.com/cvg/LightGlue/releases/download/v0.1_arxiv/disk_lightglue.pth",
}


class EngineResourceUnavailable(AlignmentRejected):
    """Missing admitted resources, distinct from a failed anatomical proposal."""


def verified_valis_resources(settings: dict[str, Any]) -> dict[str, Path]:
    resources = {}
    for name, url in VALIS_RESOURCE_URLS.items():
        path = Path(str(settings.get(f"valis{name}WeightsPath", "")))
        expected = settings.get(f"valis{name}WeightsSha256")
        if not isinstance(expected, str) or re.fullmatch("[0-9a-f]{64}", expected) is None:
            raise EngineResourceUnavailable("verified local VALIS weights unavailable")
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 64 * 1024 * 1024:
            raise EngineResourceUnavailable("verified local VALIS weights unavailable")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise EngineResourceUnavailable(
                "verified local VALIS weights differ from their admitted digest"
            )
        resources[url] = path
    return resources


@contextmanager
def admitted_valis_resources(settings: dict[str, Any]) -> Iterator[None]:
    # Admission precedes Torch/model import and never discovers a global cache.
    resources = verified_valis_resources(settings)
    torch = importlib.import_module("torch")

    original = torch.hub.load_state_dict_from_url

    def local_weights(url: str, *args: Any, **kwargs: Any) -> Any:
        if url not in resources:
            raise EngineResourceUnavailable("unadmitted VALIS pretrained resource request")
        return torch.load(
            resources[url], map_location=kwargs.get("map_location", "cpu"), weights_only=True
        )

    torch.hub.load_state_dict_from_url = local_weights
    try:
        yield
    finally:
        torch.hub.load_state_dict_from_url = original
