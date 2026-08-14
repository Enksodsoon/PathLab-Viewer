#!/usr/bin/env bash
set -Eeuo pipefail

PATHLAB_PRODUCTION_SERVICES=$'api\ncaddy\nclassroom\ntile-service\ntusd\nworker'

fail() {
  echo "Load observation failed: $*" >&2
  exit 1
}

pathlab_expected_services() {
  local configured="${1:-}"
  case "${configured}" in
    "${PATHLAB_PRODUCTION_SERVICES}")
      printf '%s\n' "${configured}"
      ;;
    *)
      return 1
      ;;
  esac
}

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

read_disk_io() {
  awk '$3 !~ /^(loop|ram)/ { read += $6; written += $10 } END { printf "%.0f %.0f\n", read*512, written*512 }' /proc/diskstats
}

main() {
  local live_dir="/opt/pathlab-viewer"
  local duration="${1:-}"
  local start_epoch="${2:-}"
  local interval=10

  [[ "${EUID}" -eq 0 ]] || fail "this script must run as root"
  [[ "${duration}" =~ ^[0-9]{2,5}$ ]] || \
    fail "duration must be an integer from 10 to 10000 seconds"
  (( duration >= 10 && duration <= 10000 && duration % interval == 0 )) || \
    fail "duration must be a multiple of 10 from 10 to 10000 seconds"
  if [[ -n "${start_epoch}" ]]; then
    [[ "${start_epoch}" =~ ^[0-9]{10}$ ]] || fail "synchronized start epoch is invalid"
    local sleep_seconds="$((start_epoch - interval - $(date +%s)))"
    (( sleep_seconds >= 0 && sleep_seconds <= 600 )) || fail "synchronized start is outside its bounded lead"
    (( sleep_seconds == 0 )) || sleep "${sleep_seconds}"
  fi
  [[ -f "${live_dir}/deploy/.env" ]] || fail "live environment is missing"

  local domain
  domain="$(sed -n 's/^DOMAIN=//p' "${live_dir}/deploy/.env" | tail -n 1)"
  domain="${domain%\"}"
  domain="${domain#\"}"
  domain="${domain%\'}"
  domain="${domain#\'}"
  [[ "${domain}" =~ ^[A-Za-z0-9.-]+$ ]] || fail "DOMAIN is missing or invalid"
  local health_url="https://${domain}/readyz"
  local release_sha
  release_sha="$(cat "${live_dir}/.pathlab-release" 2>/dev/null || true)"
  [[ "${release_sha}" =~ ^[0-9a-f]{40}$ ]] || fail "live release marker is invalid"

  local configured expected
  configured="$(
    cd "${live_dir}/deploy"
    docker compose config --services | sort
  )"
  expected=""
  pathlab_expected_services "${configured}" >/dev/null || \
    fail "configured production service topology is not approved"
  expected="${configured}"

  local previous_total previous_idle previous_rx previous_tx previous_disk_read previous_disk_write
  read -r previous_total previous_idle < <(read_cpu)
  read -r previous_rx previous_tx < <(read_network)
  read -r previous_disk_read previous_disk_write < <(read_disk_io)
  local samples=$((duration / interval))

  for _ in $(seq 1 "${samples}"); do
    sleep "${interval}"
    local current_total current_idle current_rx current_tx current_disk_read current_disk_write
    read -r current_total current_idle < <(read_cpu)
    read -r current_rx current_tx < <(read_network)
    read -r current_disk_read current_disk_write < <(read_disk_io)
    local cpu_pct memory_pct swap_used_bytes disk_free_pct
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
    disk_free_pct="$(df -P "${live_dir}" | awk 'NR == 2 { gsub("%", "", $5); printf "%.1f", 100-$5 }')"
    local ready=false
    if curl --fail --silent --show-error --max-time 5 "${health_url}" >/dev/null; then
      ready=true
    fi
    local running
    running="$(
      cd "${live_dir}/deploy"
      docker compose ps --status running --services | sort
    )"
    local services_exact=false
    [[ "${running}" == "${expected}" ]] && services_exact=true
    local restart_count=0
    local classroom_restart_count=0
    local oom_killed=false
    local sockets=0 file_descriptors=0 container_cpu_pct=0 container_memory_pct=0
    sockets="$(ss -Htan 2>/dev/null | wc -l)"
    local service container_id service_restarts service_oom container_pid service_fds
    for service in ${expected}; do
      container_id="$(cd "${live_dir}/deploy" && docker compose ps -q "${service}")"
      if [[ -z "${container_id}" ]]; then
        services_exact=false
        continue
      fi
      read -r service_restarts service_oom < <(
        docker inspect --format '{{.RestartCount}} {{.State.OOMKilled}}' "${container_id}"
      )
      restart_count=$((restart_count + service_restarts))
      [[ "${service}" != "classroom" ]] || classroom_restart_count="${service_restarts}"
      [[ "${service_oom}" == "true" ]] && oom_killed=true
      container_pid="$(docker inspect --format '{{.State.Pid}}' "${container_id}")"
      if [[ "${container_pid}" =~ ^[1-9][0-9]*$ && -d "/proc/${container_pid}/fd" ]]; then
        service_fds="$(find "/proc/${container_pid}/fd" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)"
        file_descriptors=$((file_descriptors + service_fds))
      fi
    done
    read -r container_cpu_pct container_memory_pct < <(
      cd "${live_dir}/deploy"
      docker stats --no-stream --format '{{.CPUPerc}} {{.MemPerc}}' | \
        awk '{gsub("%","",$1); gsub("%","",$2); cpu+=$1; memory+=$2} END {printf "%.1f %.1f\n", cpu/2, memory}'
    )
    printf '{"timestamp":"%s","releaseSha":"%s","ready":%s,"cpuPct":%s,"memoryPct":%s,' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${release_sha}" "${ready}" "${cpu_pct}" "${memory_pct}"
    printf '"swapUsedBytes":%s,"diskFreePct":%s,"networkRxBytesDelta":%s,' \
      "${swap_used_bytes}" "${disk_free_pct}" "$((current_rx - previous_rx))"
    printf '"networkTxBytesDelta":%s,"diskReadBytesDelta":%s,"diskWriteBytesDelta":%s,' \
      "$((current_tx - previous_tx))" "$((current_disk_read - previous_disk_read))" "$((current_disk_write - previous_disk_write))"
    printf '"sockets":%s,"fileDescriptors":%s,"containerCpuPct":%s,"containerMemoryPct":%s,' \
      "${sockets}" "${file_descriptors}" "${container_cpu_pct}" "${container_memory_pct}"
    printf '"servicesExact":%s,"restartCount":%s,"classroomRestartCount":%s,"oomKilled":%s}\n' \
      "${services_exact}" "${restart_count}" "${classroom_restart_count}" "${oom_killed}"
    previous_total="${current_total}"
    previous_idle="${current_idle}"
    previous_rx="${current_rx}"
    previous_tx="${current_tx}"
    previous_disk_read="${current_disk_read}"
    previous_disk_write="${current_disk_write}"
  done
}

if [[ "${PATHLAB_OBSERVER_LIBRARY:-0}" != "1" ]]; then
  main "$@"
fi
