from __future__ import annotations

import argparse
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response

from .config import Settings
from .conversion import configure_libvips
from .ome_tiles import MemoryTileCache, OmeTileRenderer, load_ome_tile_index
from .storage import StorageLayout
from .tile_cache import TileCache
from .tile_routes import TileRouteService, authorize_tile


def _cache_root(settings: Settings) -> Path:
    if settings.tile_cache_root.is_absolute():
        return settings.tile_cache_root
    return settings.data_root / "cache" / "ome-tiles"


def _renderer(settings: Settings) -> OmeTileRenderer:
    return OmeTileRenderer(
        TileCache(
            _cache_root(settings),
            max_bytes=settings.tile_cache_max_bytes,
            low_water_bytes=settings.tile_cache_low_water_bytes,
            max_temp_bytes=settings.tile_cache_max_temp_bytes,
        ),
        memory_cache=MemoryTileCache(settings.tile_cache_memory_bytes),
        render_concurrency=settings.tile_render_concurrency,
    )


def create_tile_app(settings: Settings | None = None) -> FastAPI:
    current = settings or Settings()
    storage = StorageLayout(current.data_root, current.storage_cap_bytes)
    services: dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        routes = TileRouteService(storage, _renderer(current))
        services["routes"] = routes
        try:
            yield
        finally:
            services.pop("routes", None)
            routes.close()

    app = FastAPI(
        title="PathLab Viewer Internal Tile Service",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def routes() -> TileRouteService:
        service = services.get("routes")
        if not isinstance(service, TileRouteService):
            raise HTTPException(status_code=503, detail={"code": "TILE_SERVICE_UNAVAILABLE"})
        return service

    @app.get("/livez")
    def livez() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/readyz")
    def readyz() -> dict[str, int | str]:
        service = routes()
        renderer = service.renderer
        if renderer is None:
            raise HTTPException(status_code=503, detail={"code": "TILE_SERVICE_UNAVAILABLE"})
        stats = renderer.persistent_cache.stats()
        if stats.tile_bytes > current.tile_cache_max_bytes:
            raise HTTPException(status_code=503, detail={"code": "TILE_CACHE_UNBOUNDED"})
        originals = current.data_root / "originals"
        known_index = next(originals.glob("*/tile-index.json"), None)
        if known_index is not None:
            load_ome_tile_index(known_index)
        return {
            "status": "ready",
            "cacheBytes": stats.tile_bytes,
            "cacheMaxBytes": current.tile_cache_max_bytes,
        }

    @app.get("/_pathlab_ome/{slide_id}/{slide_sha256}/{tile_path:path}")
    def dynamic_tile(
        slide_id: str,
        slide_sha256: str,
        tile_path: str,
    ) -> Response:
        if re.fullmatch(r"[0-9a-f]{64}", slide_sha256) is None:
            raise HTTPException(status_code=404, detail={"code": "TILE_NOT_FOUND"})
        return routes().dynamic_response(
            authorize_tile(
                slide_id=slide_id,
                slide_sha256=slide_sha256,
                render_mode="ome_dynamic",
                relative_path=tile_path,
                cache_control="private, max-age=86400, immutable",
            )
        )

    return app


app = create_tile_app()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--purge-cache", action="store_true")
    arguments = parser.parse_args()
    settings = Settings()
    if arguments.purge_cache:
        cache = TileCache(
            _cache_root(settings),
            max_bytes=settings.tile_cache_max_bytes,
            low_water_bytes=settings.tile_cache_low_water_bytes,
            max_temp_bytes=settings.tile_cache_max_temp_bytes,
        )
        try:
            cache.purge()
        finally:
            cache.close()
        return
    configure_libvips(
        concurrency=settings.libvips_concurrency,
        cache_max_mem_bytes=settings.libvips_cache_max_mem_bytes,
        cache_max_files=settings.libvips_cache_max_files,
        cache_max_operations=settings.libvips_cache_max_operations,
    )
    import uvicorn

    uvicorn.run(
        "wsi_viewer.tile_service:app",
        host="0.0.0.0",
        port=8090,
        workers=1,
        proxy_headers=False,
    )
