#!/usr/bin/env bash
set -euo pipefail

: "${DUCKDNS_SUBDOMAIN:?DUCKDNS_SUBDOMAIN is required}"
: "${DUCKDNS_TOKEN:?DUCKDNS_TOKEN is required}"

[[ "$DUCKDNS_SUBDOMAIN" =~ ^[A-Za-z0-9-]+$ ]]
[[ "$DUCKDNS_TOKEN" != *$'\n'* && "$DUCKDNS_TOKEN" != *$'\r'* ]]

response="$(
  printf '%s\n' \
    'url = "https://www.duckdns.org/update"' \
    "data-urlencode = \"domains=${DUCKDNS_SUBDOMAIN}\"" \
    "data-urlencode = \"token=${DUCKDNS_TOKEN}\"" \
    'data = "ip="' |
    curl --fail --silent --show-error --max-time 15 --config -
)"
test "$response" = "OK"
