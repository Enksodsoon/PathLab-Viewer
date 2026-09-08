# Assessment host observer

The observer is a root-operated read-only collector for an isolated eight-service
qualification stack. It does not enable Assessment, provision a public endpoint,
or certify capacity. The production database cutover is a separate operation.

Use the reviewed `deploy/scripts/assessment_host_observer.py` from the target
release. Its JSON configuration must be a root-owned regular file with no group
or other permissions. It contains:

- `releaseSha`: the exact 40-character release SHA.
- `liveDir`: the canonical release directory containing `.pathlab-release`.
- `databaseUser` and `databaseName`: the target PostgreSQL identifiers.
- `containers`: a mapping from `api`, `classroom`, `assessment`, `postgres`,
  `tile-service`, `worker`, `caddy`, and `tusd` to their distinct full Docker IDs.

Pin IDs after starting the qualification stack; do not resolve a mutable name on
each sample. All application images must carry the requested SHA tag. PostgreSQL
must report version 18.6. The host must expose Docker container cgroup-v2 memory
events. Missing health, workers, counters, or cgroups fails measurement closed.

Configure `PATHLAB_CAPACITY_OBSERVER_TOKEN` in the isolated stack for the internal
count-only pressure endpoints. Use a different random token, stored in a second
root-only regular file, for access to the host observer. Neither token belongs in
commands, Git, logs, screenshots, or evidence artifacts.

First run a complete measured sample:

```sh
sudo python3 deploy/scripts/assessment_host_observer.py \
  --config /etc/pathlab-viewer/assessment-observer.json --once
```

Then launch the supervised collector:

```sh
sudo systemd-run --unit=pathlab-assessment-observer --property=Type=exec \
  /usr/bin/python3 /opt/pathlab-viewer/deploy/scripts/assessment_host_observer.py \
  --config /etc/pathlab-viewer/assessment-observer.json \
  --token-file /etc/pathlab-viewer/assessment-observer.token
```

The listener binds only `127.0.0.1:5331`. `GET /sample` requires the dedicated
Bearer token. A protected HTTPS route to that loopback endpoint must be
established separately before configuring the GitHub campaign. Do not publish a
plaintext host port or expose inherited staging identities to establish access.

For a proxy on the same host, `--unix-socket` selects a new socket in an existing
root-owned mode-0700 directory instead of a TCP listener. Mount only that socket
directory into the HTTPS proxy. An existing socket is refused; after stopping
the old observer, inspect and remove its stale socket before restarting.

Use `--cohost-production` for a campaign sharing the production machine. It holds
the existing protected capacity-controller lock for the observer lifetime, so
normal production deployments and other capacity operations cannot overlap.
Keep the observer alive through campaign cleanup, then stop it to release the
lock. This option does not stop production services or authorize a campaign.

The collector samples every five seconds after completing its previous sample.
An empty, failed, future-dated, or more-than-20-second-old cache returns HTTP 503.
The campaign client also rejects stale samples and requires all four distinct
API/Classroom/Assessment pool generations, including both Assessment workers.
These are the request-serving pressure roles; drain conversion/background work
and keep Classroom idle for the Assessment campaign.

Counters retain observed failures from pool startup. A worker replacement or
counter decrease invalidates collection; restart the qualification setup rather
than discarding those failures. OOM counts come from each pinned container's
host cgroup, including containers without a shell. Restart counts come from
Docker, connection counts from PostgreSQL, and CPU/memory/swap from host kernel
counters. No SQL text, query parameters, answers, or user identifiers are retained.

CPU utilization spans successive collection endpoints, including the five-second
pause between polls and the cost of collecting measurements. The first sample
(also in `--once` mode) waits five seconds to establish an interval. Measuring only
the collection burst would overstate CPU pressure on an otherwise idle host.
