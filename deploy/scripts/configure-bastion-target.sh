#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_USER="pathlab-deploy"
ENTRYPOINT="/usr/local/sbin/pathlab-viewer-deploy-entrypoint"
SSHD_CONFIG="/etc/ssh/sshd_config.d/90-pathlab-deploy.conf"
SUDOERS_CONFIG="/etc/sudoers.d/pathlab-deploy"

[[ "${EUID}" -eq 0 ]] || {
  echo "This script must run as root." >&2
  exit 1
}

if ! id -u "${DEPLOY_USER}" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/sh "${DEPLOY_USER}"
fi
passwd --lock "${DEPLOY_USER}" >/dev/null

entrypoint_file="$(mktemp)"
sshd_file="$(mktemp)"
sudoers_file="$(mktemp)"
trap 'rm -f -- "${entrypoint_file}" "${sshd_file}" "${sudoers_file}"' EXIT

printf '%s\n' \
  '#!/bin/sh' \
  'exec sudo -n /usr/local/sbin/pathlab-viewer-deploy "${SSH_ORIGINAL_COMMAND:-}"' \
  > "${entrypoint_file}"

printf '%s\n' \
  'Match User pathlab-deploy' \
  '    AuthenticationMethods publickey' \
  '    PasswordAuthentication no' \
  '    KbdInteractiveAuthentication no' \
  '    DisableForwarding yes' \
  '    PermitTTY no' \
  '    ForceCommand /usr/local/sbin/pathlab-viewer-deploy-entrypoint' \
  > "${sshd_file}"

printf '%s\n' \
  'pathlab-deploy ALL=(root) NOPASSWD: /usr/local/sbin/pathlab-viewer-deploy *' \
  > "${sudoers_file}"

install -o root -g root -m 755 "${entrypoint_file}" "${ENTRYPOINT}"
install -o root -g root -m 644 "${sshd_file}" "${SSHD_CONFIG}"
install -o root -g root -m 440 "${sudoers_file}" "${SUDOERS_CONFIG}"

visudo -cf "${SUDOERS_CONFIG}" >/dev/null
sshd -t
systemctl reload ssh
