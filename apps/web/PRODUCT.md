# PathLab Viewer product record

PathLab Viewer is a private-first web application for reviewing and publishing
OME-TIFF whole-slide images. An authenticated administrator uploads an original
slide; the server validates it and produces sanitized Deep Zoom JPEG tiles for
browser viewing. Original slide files remain private.

## Product boundaries

- Authentication, storage, conversion, publication, and sharing contracts are
  backend-owned and must not change during visual work.
- Public slides, folders, and collections use unlisted, read-only links.
- Viewer imagery remains natural-color and is never filtered or inverted by a
  user-interface theme.
- Existing routes, URL state, keyboard behavior, dialogs, focus restoration,
  upload flow, and OpenSeadragon lifecycle are product contracts.

## Theme contract

The web client offers `light`, `dark`, and `system` preferences. New users use
`system`; explicit selections persist locally under `pathlab-theme:v1`. The
resolved mode is written as `data-theme="light"` or `data-theme="dark"` on the
document root before React starts.
