#!/usr/bin/env bash
set -Eeuo pipefail

LIVE_DIR="/opt/pathlab-viewer"
DURATION="${1:-}"
INTERVAL=10

fail() {
  echo "Load observation failed: $*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "this script must run as root"
[[ "${DURATION}" =~ ^[0-9]{2,3}$ ]] || fail "duration must be an integer from 10 to 900 seconds"
(( DURATION >= 10 && DURATION <= 900 && DURATION % INTERVAL == 0 )) || \
  fail "duration must be a multiple of 10 from 10 to 900 seconds"
[[ -f "${LIVE_DIR}/deploy/.env" ]] || fail "live environment is missing"

DOMAIN="$(sed -n 's/^DOMAIN=//p' "${LIVE_DIR}/deploy/.env" | tail -n 1)"
DOMAIN="${DOMAIN%\"}"
DOMAIN="${DOMAIN#\"}"
DOMAIN="${DOMAIN%\'}"
DOMAIN="${DOMAIN#\'}"
[[ "${DOMAIN}" =~ ^[A-Za-z0-9.-]+$ ]] || fail "DOMAIN is missing or invalid"
HEALTH_URL="https://${DOMAIN}/readyz"
RELEASE_SHA="$(cat "${LIVE_DIR}/.pathlab-release" 2>/dev/null || true)"
[[ "${RELEASE_SHA}" =~ ^[0-9a-f]{40}$ ]] || fail "live release marker is invalid"

read_cpu() {
  awk '/^cpu / {
    idle=$5+$6
    total=0
    for (i=2; i<=NF; i++) total+=$i
    printf "%.0f %.0f\n", total, idle
  }' /proc/stat
}

read_network() {
  awk -F '[: ]+' '
    NR > 2 && $2 != "lo" { rx += $3; tx += $11 }
    END { printf "%.0f %.0f\n", rx, tx }
  ' /proc/net/dev
}

read -r previous_total previous_idle < <(read_cpu)
read -r previous_rx previous_tx < <(read_network)
samples=$((DURATION / INTERVAL))

for _ in $(seq 1 "${samples}"); do
  sleep "${INTERVAL}"
  read -r current_total current_idle < <(read_cpu)
  read -r current_rx current_tx < <(read_network)
  cpu_pct="$(awk -v total="$((current_total - previous_total))" \
    -v idle="$((current_idle - previous_idle))" \
    'BEGIN { if (total <= 0) print "0.0"; else printf "%.1f", 100 * (total-idle) / total }')"
  memory_pct="$(awk '
    /^MemTotal:/ { total=$2 }
    /^MemAvailable:/ { available=$2 }
    END { if (total <= 0) print "0.0"; else printf "%.1f", 100 * (total-available) / total }
  ' /proc/meminfo)"
  swap_used_bytes="$(awk '
    /^SwapTotal:/ { total=$2 }
    /^SwapFree:/ { free=$2 }
    END { printf "%.0f", (total-free) * 1024 }
  ' /proc/meminfo)"
  disk_free_pct="$(df -P "${LIVE_DIR}" | awk 'NR == 2 { gsub("%", "", $5); printf "%.1f", 100-$5 }')"
  ready=false
  if curl --fail --silent --show-error --max-time 5 "${HEALTH_URL}" >/dev/null; then
    ready=true
  fi
  running="$(
    cd "${LIVE_DIR}/deploy"
    docker compose ps --status running --services | sort
  )"
  expected=$'api\ncaddy\ntusd\nworker'
  services_exact=false
  [[ "${running}" == "${expected}" ]] && services_exact=true
  restart_count=0
  oom_killed=false
  for service in api caddy tusd worker; do
    container_id="$(cd "${LIVE_DIR}/deploy" && docker compose ps -q "${service}")"
    if [[ -z "${container_id}" ]]; then
      services_exact=false
      continue
    fi
    read -r service_restarts service_oom < <(
      docker inspect --format '{{.RestartCount}} {{.State.OOMKilled}}' "${container_id}"
    )
    restart_count=$((restart_count + service_restarts))
    [[ "${service_oom}" == "true" ]] && oom_killed=true
  done
  printf '{"timestamp":"%s","releaseSha":"%s","ready":%s,"cpuPct":%s,"memoryPct":%s,' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${RELEASE_SHA}" "${ready}" "${cpu_pct}" "${memory_pct}"
  printf '"swapUsedBytes":%s,"diskFreePct":%s,"networkRxBytesDelta":%s,' \
    "${swap_used_bytes}" "${disk_free_pct}" "$((current_rx - previous_rx))"
  printf '"networkTxBytesDelta":%s,"servicesExact":%s,"restartCount":%s,"oomKilled":%s}\n' \
    "$((current_tx - previous_tx))" "${services_exact}" "${restart_count}" "${oom_killed}"
  previous_total="${current_total}"
  previous_idle="${current_idle}"
  previous_rx="${current_rx}"
  previous_tx="${current_tx}"
done
