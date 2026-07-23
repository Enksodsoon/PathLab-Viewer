# OCI Deployment Runbook

This runbook covers the repository's single-host OCI deployment. Read [`docs/PROJECT_GUIDE.md`](../docs/PROJECT_GUIDE.md) for the application architecture and privacy boundaries.

The checked-in Terraform configuration targets one Arm-based compute instance, a boot volume, and a separate application-data volume. Cloud pricing, public IPv4 charges, quotas, and promotional eligibility can change. Review the current Terraform plan, OCI cost estimator, tenancy limits, and billing page before creating or updating resources.

## Initial deployment

1. Copy `deploy/terraform/terraform.tfvars.example` to `deploy/terraform/terraform.tfvars` and fill in the tenancy-specific values.
2. Run `terraform plan` and review every resource, size, network rule, and estimated cost before applying.
3. Point the configured DNS name at the instance public address.
4. Copy `deploy/.env.example` to `deploy/.env` and generate `PATHLAB_SECRET_KEY` with `openssl rand -hex 32`.
5. Clone the repository to `/opt/pathlab-viewer`.
6. Mount the application data volume at `/srv/pathlab/data` and set ownership with `sudo chown -R 10001:10001 /srv/pathlab/data`.
7. Install `deploy/pathlab-viewer.service`, then run `sudo systemctl enable --now pathlab-viewer`.
8. Create the administrator with `docker compose -f deploy/compose.yaml exec api pathlab-admin create-admin`.
9. Schedule `deploy/scripts/duckdns.sh` if DuckDNS is used and schedule `deploy/scripts/backup.sh` daily.
10. Store at least one encrypted backup outside the application VM.

Do not apply a plan that introduces unexpected paid services, open management ports, unreviewed storage changes, or resources outside the intended tenancy and region.

## Routine operations

- Readiness: `curl --fail https://$DOMAIN/readyz`
- Liveness: `curl --fail https://$DOMAIN/livez`
- Logs: `docker compose -f deploy/compose.yaml logs --since 30m api worker tusd caddy`
- Backup: `PATHLAB_BACKUP_DIR=/mnt/backup deploy/scripts/backup.sh`
- Compose validation: `docker compose -f deploy/compose.yaml config`

Each service uses bounded Docker `json-file` log rotation. Review container health, disk usage, database readiness, backup age, and public tile delivery after every deployment.

## Production deployment workflow

Use **Actions → Deploy production → Run workflow** from the current reviewed default branch. The protected `production` environment requires approval, deploys the selected reviewed commit, verifies readiness, and restores the prior release when verification fails.

The previous release is retained under `/opt/pathlab-viewer.rollback-*` for manual rollback. Confirm the active release from the host or workflow output; do not record a temporary commit hash in this runbook.

## OCI Bastion setup

The deployment workflow creates a temporary OCI Bastion managed SSH session for each approved deployment and deletes it when the job exits. Administrator SSH remains the break-glass path.

1. Enable the OCI Bastion agent plugin and create a Standard Bastion in the instance VCN.
2. Permit the Bastion private endpoint to reach target port 22.
3. Install `deploy/scripts/deploy-release.sh` as the root-owned executable `/usr/local/sbin/pathlab-viewer-deploy`.
4. Run `sudo deploy/scripts/configure-bastion-target.sh` to create the password-locked `pathlab-deploy` user and force deployment sessions through the validated script.
5. Create a dedicated OCI API user with only the permissions needed to create, read, and delete sessions for the deployment Bastion.
6. Configure the GitHub `production` environment with variables `OCI_BASTION_ID`, `OCI_INSTANCE_ID`, and `OCI_TARGET_PRIVATE_IP`.
7. Configure secrets `OCI_CONFIG`, `OCI_API_PRIVATE_KEY`, and `OCI_BASTION_KNOWN_HOSTS`.

`OCI_CONFIG` should reference `/home/runner/.oci/oci_api_key.pem`. `OCI_BASTION_KNOWN_HOSTS` must pin both the Bastion endpoint and target host keys.

Scope the OCI policy to the deployment Bastion, target instance, and `pathlab-deploy` operating-system user. Restrict session creation to the target instance and username, grant only required read access to instance, network, agent-plugin, and Bastion-session metadata, and do not use an administrator API key.

The deployment workflow must never read or modify `/srv/pathlab/data` except through the deployed application services and approved backup or restore procedures.

## Backup and restore

Run backups on a fixed schedule and monitor their age and size. A backup is not considered verified until it has been restored successfully.

Perform restore drills on a disposable host:

```bash
deploy/scripts/restore.sh --confirm /absolute/path/to/backup
```

After restoration, compare slide records, SHA-256 values, manifests, representative DZI descriptors, representative JPEG tiles, authentication behavior, and readiness endpoints. Never test restoration directly over the only production data copy.

## Viewer load testing

Create a manifest from sanitized public derivatives on the host. Supply public identifiers explicitly; the tooling never discovers or selects them:

```bash
python tests/load/generate_manifest.py \
  --public-root /srv/pathlab/data/public \
  --public-id '<public-id>' \
  --output /absolute/path/to/viewer-load-manifest.json \
  --seed 1
```

Run the local smoke profile:

```bash
BASE_URL="$BASE_URL" \
MANIFEST_PATH=/absolute/path/to/viewer-load-manifest.json \
deploy/scripts/run-viewer-load-test.sh smoke
```

Run `acceptance` only in an authorized external test window. It uses 100 virtual users for 10 minutes. The wrapper is never invoked by deployment or CI and requires an operator-provided URL and manifest.

## Optional CDN policy

A CDN is optional and is not required for PathLab Viewer.

- Cache only `/tiles/*` and `/assets/*`, respecting the origin `s-maxage`.
- Bypass `/api/*`, `/api/v1/uploads/*`, `/admin`, `/s/*`, `/livez`, and `/readyz`.
- Keep credentials, provider tokens, zone identifiers, and private URLs outside the repository.
- Do not claim immediate revocation of content already retained in a browser cache.

No provider-specific configuration, paid feature, cache daemon, or purge integration is required.

## Administrator password recovery

Generate a single-use recovery code on the server:

```bash
docker compose -f deploy/compose.yaml exec api \
  pathlab-admin issue-recovery-code --username admin
```

The code expires after 15 minutes and invalidates earlier unused codes. Enter it only in the HTTPS **Forgot password** form. The command prints the code once; do not place it in shell arguments, logs, screenshots, tickets, or documentation.

For a console-only emergency reset:

```bash
docker compose -f deploy/compose.yaml exec api \
  pathlab-admin reset-password --username admin
```

Password change, recovery, and emergency reset revoke existing sessions and unused recovery codes. See [`docs/architecture/PASSWORD_RECOVERY.md`](../docs/architecture/PASSWORD_RECOVERY.md) for the security contract.

## Post-deployment checks

1. Confirm `/livez` and `/readyz` return success.
2. Confirm the administrator can sign in without exposing credentials in logs.
3. Confirm an existing private slide remains private.
4. Confirm a published slide's metadata, DZI descriptor, and representative JPEG tile load over HTTPS.
5. Confirm upload admission and available storage reporting are accurate.
6. Confirm backup scheduling and off-host backup availability.
7. Review the current billing page and resource inventory.
8. Record environment-specific evidence outside general product documentation.
