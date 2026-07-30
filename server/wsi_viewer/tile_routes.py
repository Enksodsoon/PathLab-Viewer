from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from fastapi import HTTPException, Response

from .ome_tiles import (
    DynamicSlide,
    DziRequest,
    OmeTileError,
    OmeTileRenderer,
    load_ome_tile_index,
)
from .storage import StorageLayout
from .tile_cache import TileCacheError

_DZI_TILE = re.compile(
    r"^slide_files/(?P<level>[0-9]{1,3})/"
    r"(?P<column>[0-9]{1,9})_(?P<row>[0-9]{1,9})\.(?:jpg|jpeg)$"
)


@dataclass(frozen=True, slots=True)
class AuthorizedTile:
    slide_id: str
    slide_sha256: str
    render_mode: Literal["static_dzi", "ome_dynamic"]
    relative_path: str
    cache_control: str


def authorize_tile(
    *,
    slide_id: str,
    slide_sha256: str | None,
    render_mode: str,
    relative_path: str,
    cache_control: str,
) -> AuthorizedTile:
    if render_mode not in {"static_dzi", "ome_dynamic"}:
        raise HTTPException(status_code=404, detail={"code": "TILE_NOT_FOUND"})
    if render_mode == "ome_dynamic" and (
        slide_sha256 is None or not re.fullmatch(r"[0-9a-f]{64}", slide_sha256)
    ):
        raise HTTPException(status_code=503, detail={"code": "TILE_UNAVAILABLE"})
    return AuthorizedTile(
        slide_id=slide_id,
        slide_sha256=slide_sha256 or "0" * 64,
        render_mode=cast(Literal["static_dzi", "ome_dynamic"], render_mode),
        relative_path=relative_path,
        cache_control=cache_control,
    )


class TileRouteService:
    def __init__(
        self,
        storage: StorageLayout,
        renderer: OmeTileRenderer | None,
        *,
        internal_redirects: bool = False,
    ) -> None:
        if not internal_redirects and renderer is None:
            raise ValueError("Local dynamic tile routing requires a renderer")
        self.storage = storage
        self.renderer = renderer
        self.internal_redirects = internal_redirects

    def dynamic_response(self, tile: AuthorizedTile) -> Response:
        if tile.render_mode != "ome_dynamic":
            raise ValueError("Dynamic tile service received a static slide")
        self._validate_relative_path(tile.relative_path)
        if self.internal_redirects:
            return Response(
                status_code=200,
                headers={
                    "X-Accel-Redirect": (
                        f"/_pathlab_ome/{tile.slide_id}/"
                        f"{tile.slide_sha256}/{tile.relative_path}"
                    ),
                    "Cache-Control": tile.cache_control,
                    "X-Content-Type-Options": "nosniff",
                },
            )
        if self.renderer is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "TILE_SERVICE_UNAVAILABLE"},
            )
        try:
            slide = self._dynamic_slide(tile)
            if tile.relative_path == "slide.dzi":
                payload = self.renderer.descriptor(slide)
                media_type = "application/xml"
            elif tile.relative_path == "thumbnail.jpg":
                payload = self.renderer.thumbnail(slide)
                media_type = "image/jpeg"
            else:
                match = _DZI_TILE.fullmatch(tile.relative_path)
                if match is None:
                    raise HTTPException(
                        status_code=404,
                        detail={"code": "TILE_NOT_FOUND"},
                    )
                payload = self.renderer.tile(
                    slide,
                    DziRequest(
                        level=int(match["level"]),
                        column=int(match["column"]),
                        row=int(match["row"]),
                    ),
                )
                media_type = "image/jpeg"
        except HTTPException:
            raise
        except OmeTileError as error:
            if "out of bounds" in str(error):
                raise HTTPException(
                    status_code=404,
                    detail={"code": "TILE_NOT_FOUND"},
                ) from error
            raise HTTPException(
                status_code=503,
                detail={"code": "TILE_UNAVAILABLE"},
            ) from error
        except (OSError, TileCacheError, ValueError) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "TILE_UNAVAILABLE"},
            ) from error

        etag = hashlib.sha256(
            f"{tile.slide_sha256}:{tile.relative_path}".encode("ascii")
        ).hexdigest()
        return Response(
            content=payload,
            media_type=media_type,
            headers={
                "Cache-Control": tile.cache_control,
                "ETag": f'"{etag}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @staticmethod
    def _validate_relative_path(relative_path: str) -> None:
        if relative_path in {"slide.dzi", "thumbnail.jpg"}:
            return
        if _DZI_TILE.fullmatch(relative_path) is None:
            raise HTTPException(status_code=404, detail={"code": "TILE_NOT_FOUND"})

    def _dynamic_slide(self, tile: AuthorizedTile) -> DynamicSlide:
        paths = self.storage.for_slide(tile.slide_id)
        index = load_ome_tile_index(paths.ome_index)
        if index.source_sha256 != tile.slide_sha256:
            raise OmeTileError("Dynamic OME hash does not match its authorization")
        return DynamicSlide(
            source=paths.original,
            index=paths.ome_index,
            sha256=tile.slide_sha256,
            width=index.width,
            height=index.height,
            quality=95,
            quality_profile="ome-dynamic-v1-q95",
        )

    def close(self) -> None:
        if self.renderer is not None:
            self.renderer.close()

    def purge_slide(self, slide_sha256: str | None) -> int:
        if slide_sha256 is None or self.renderer is None:
            return 0
        return self.renderer.persistent_cache.purge_slide(slide_sha256)


def private_static_target(storage: StorageLayout, slide_id: str, tile_path: str) -> Path:
    root = storage.for_slide(slide_id).private_derivative.resolve()
    target = (root / tile_path).resolve()
    if (
        not target.is_relative_to(root)
        or target.suffix.lower() not in {".dzi", ".jpg", ".jpeg"}
        or not target.is_file()
    ):
        raise HTTPException(status_code=404, detail={"code": "TILE_NOT_FOUND"})
    return target
