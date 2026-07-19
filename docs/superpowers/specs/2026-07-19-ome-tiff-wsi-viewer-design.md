# PathLab Viewer OME-TIFF WSI Design

PathLab Viewer is a compact public whole-slide image viewer for one administrator and up to 100 independent anonymous viewers. The administrator uploads OME-TIFF files up to 5 GiB, reviews generated DZI derivatives privately, and publishes unlisted read-only links. Originals remain private.

Accepted inputs are valid two-dimensional RGB OME-TIFF files with `SizeZ=1` and `SizeT=1`. Classic TIFF and BigTIFF, either endianness, flat or pyramidal, tiled or striped, unsigned 8/16-bit samples, and JPEG/LZW/Deflate/uncompressed payloads are supported. Sixteen-bit samples map linearly to eight-bit output. Non-OME ImageJ TIFF is rejected.

The runtime is Caddy, FastAPI, tusd, one conversion worker, SQLite WAL, and filesystem-backed storage. The worker validates OME metadata, converts the highest-resolution primary series with libvips to complete 512-pixel JPEG DZI tiles, removes generator metadata, validates the derivative tree, and atomically publishes it.

Visual direction is clinical editorial modernism: true white surfaces, deep navy text, cool gray dividers, restrained teal actions, minimal coral destructive treatment, thin borders, almost no shadow, and the tissue canvas as the visual focus.

