#!/usr/bin/env bash
set -Eeuo pipefail

: "${OCI_CONFIG:?OCI_CONFIG is required}"
: "${OCI_API_PRIVATE_KEY:?OCI_API_PRIVATE_KEY is required}"
: "${OCI_BASTION_KNOWN_HOSTS:?OCI_BASTION_KNOWN_HOSTS is required}"

install -d -m 700 ~/.oci ~/.ssh
printf '%s\n' "${OCI_CONFIG}" > ~/.oci/config
printf '%s\n' "${OCI_API_PRIVATE_KEY}" > ~/.oci/oci_api_key.pem
printf '%s\n' "${OCI_BASTION_KNOWN_HOSTS}" > ~/.ssh/known_hosts
chmod 600 ~/.oci/config ~/.oci/oci_api_key.pem ~/.ssh/known_hosts
