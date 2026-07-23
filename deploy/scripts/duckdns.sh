#!/usr/bin/env bash
set -euo pipefail

: "${DUCKDNS_SUBDOMAIN:?DUCKDNS_SUBDOMAIN is required}"
: "${DUCKDNS_TOKEN:?DUCKDNS_TOKEN is required}"
[[ "${DUCKDNS_SUBDOMAIN}" =~ ^[A-Za-z0-9-]+$ ]] || {
  echo "DUCKDNS_SUBDOMAIN contains unsupported characters" >&2
  exit 2
}
[[ "${DUCKDNS_TOKEN}" =~ ^[A-Za-z0-9-]+$ ]] || {
  echo "DUCKDNS_TOKEN contains unsupported characters" >&2
  exit 2
}

response="$(
  {
    printf '%s\n' 'url = "https://www.duckdns.org/update"'
    printf '%s\n' 'get'
    printf 'data-urlencode = "domains=%s"\n' "${DUCKDNS_SUBDOMAIN}"
    printf 'data-urlencode = "token=%s"\n' "${DUCKDNS_TOKEN}"
    printf '%s\n' 'data-urlencode = "ip="'
  } | curl --fail --silent --show-error --max-time 15 --config -
)"
test "${response}" = "OK"
