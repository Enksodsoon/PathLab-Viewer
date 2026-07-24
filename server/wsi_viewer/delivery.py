from pathlib import Path

from fastapi import Response
from fastapi.responses import FileResponse


def deliver_file(
    target: Path,
    *,
    data_root: Path,
    internal_redirects: bool,
    media_type: str,
    cache_control: str,
    headers: dict[str, str] | None = None,
) -> Response:
    response_headers = {"Cache-Control": cache_control, **(headers or {})}
    if not internal_redirects:
        return FileResponse(target, media_type=media_type, headers=response_headers)

    relative = target.resolve().relative_to(data_root.resolve())
    if not relative.parts or relative.parts[0] not in {"private", "public"}:
        raise ValueError("Internal delivery target is outside an approved derivative root")
    mount = f"pathlab-{relative.parts[0]}"
    redirect = "/" + "/".join((mount, *relative.parts[1:]))
    response_headers["X-Accel-Redirect"] = redirect
    return Response(status_code=200, media_type=media_type, headers=response_headers)
