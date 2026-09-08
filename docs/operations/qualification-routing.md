# Isolated qualification HTTPS routing

The default release adds no qualification hostname. Caddy imports optional
operator-owned fragments, using its documented
[empty-glob behavior](https://caddyserver.com/docs/caddyfile/directives/import).
Production fragments live in `/etc/pathlab-viewer/qualification-caddy`, outside
application data and release swaps. Their content hashes are bound into the
runtime safety manifest; adding, changing, or retiring a fragment requires
validating the resulting runtime and refreshing that manifest.

Before publishing a qualification origin, prepare an independent PostgreSQL
database, separate application secrets and sessions, and only approved test
assets. Do not expose the older full-data rehearsal target. Keep staging service
ports private, and use a different hostname so cookies cannot collide with
production sessions.

The outer Caddy joins the internal `pathlab-qualification` network. Attach only
the isolated web proxy to that network, with the unique alias
`pathlab-qualification-web`. Keep the isolated API and database on their own
networks; do not attach them to production networks or introduce another `api`
DNS alias there. Configure the isolated web proxy to trust the exact outer proxy
address so HTTPS scheme information reaches the isolated API correctly.

A qualification-only fragment can use this structure, with the actual controlled
hostname substituted by the operator:

```caddyfile
qualify.example.test {
    @host_observer path /host-observer/sample
    handle @host_observer {
        rewrite * /sample
        reverse_proxy unix//run/pathlab-assessment-observer/observer.sock {
            header_up Host localhost
        }
    }
    handle {
        reverse_proxy pathlab-qualification-web:80
    }
}
```

The observer still authenticates its dedicated Bearer token. Its
[Unix-socket upstream](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
does not require a public host port. The normal production site and its internal
API denial rules remain a separate host block.

Install or retire only the intended fragment while holding the production
deployment and capacity-controller locks. Validate the complete Caddy
configuration before reload. Preserve the previous fragment for recovery, check
production readiness and the isolated target, and refresh the runtime manifest
only after those checks pass. Stop the campaign observer after fixture cleanup
to release its cohost capacity lock before retiring the route. Do not treat a
reachable HTTPS origin as evidence of capacity or learner-pilot success.
