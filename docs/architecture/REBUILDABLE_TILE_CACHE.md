# Rebuildable tile-cache index

The dynamic OME tile cache is disposable and is not part of PathLab's durable
application state. Program 0B therefore removes its SQLite metadata database
instead of moving high-frequency LRU writes into PostgreSQL.

Cached JPEGs use this private layout:

```text
<cache-root>/<slide-sha-prefix>/<slide-sha256>/<tile-key-digest>.jpg
```

At process start, the tile service validates regular files, size bounds, hashes,
and the slide-addressed layout, then rebuilds an in-memory least-recently-used
index. File modification time establishes deterministic restart ordering; cache
hits update the order in memory without durable metadata writes. Startup removes
partial temporary files, the former `index.sqlite3` sidecars, malformed entries,
and legacy tiles whose slide ownership cannot be reconstructed safely.

Writes remain same-filesystem temporary-file plus `fsync` plus atomic-replace
operations. A single-flight map coalesces concurrent requests for the same tile.
The cache evicts to its configured low-water mark before admitting a write and
can still purge all tiles or every tile owned by a given source-slide hash after
a restart.

This change does not alter the browser tile-source contract, durable slide data,
feature activation, or deployment database. Loss of this cache only causes tiles
to be rendered again.
