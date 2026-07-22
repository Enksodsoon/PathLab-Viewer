# OCI Always Free deployment

For the plain-language architecture and project history, start with [`docs/PROJECT_GUIDE.md`](../docs/PROJECT_GUIDE.md). This file is the operator runbook for the OCI host.

This deployment uses one `VM.Standard.A1.Flex` instance, a 50 GB boot volume, and a 150 GB attached data volume. Together they consume the documented 200 GB Always Free block-volume allowance. Capacity is tenancy- and home-region-dependent; Terraform output is not proof of zero charge. Confirm every resource is marked **Always Free eligible** before applying.

## Bring-up

1. Create `deploy/terraform/terraform.tfvars` from the example and run `terraform plan`. Reject any plan that is not A1 Flex, 2 OCPUs, 12 GB RAM, 50+150 GB storage, or that adds non-free services.
2. Point the DuckDNS subdomain at the instance public IP. Put the deployment values in `deploy/.env`; generate `PATHLAB_SECRET_KEY` with `openssl rand -hex 32`.
3. Clone the repository to `/opt/pathlab-viewer`, mount the data volume at `/srv/pathlab/data`, and run `sudo chown -R 10001:10001 /srv/pathlab/data`.
4. Install `pathlab-viewer.service`, then run `sudo systemctl enable --now pathlab-viewer`.
5. Create the single administrator with `docker compose exec api pathlab-admin create-admin`.
6. Install `duckdns.sh` every five minutes and `backup.sh` daily with root-owned systemd timers or cron. Keep at least one encrypted backup outside the VM.

## Operations

- Readiness: `curl --fail https://$DOMAIN/readyz`
- Logs: `docker compose logs --since 30m api worker tusd caddy`
- Log rotation: every service uses Docker's `json-file` driver with at most three 10 MB files per container. To roll back, revert this configuration change and run `sudo systemctl reload pathlab-viewer`; Compose recreates affected containers with the previous or daemon-default logging configuration.
- Backup: `PATHLAB_BACKUP_DIR=/mnt/backup deploy/scripts/backup.sh`
- Restore drill: use a disposable VM and run `restore.sh --confirm /absolute/backup`, then compare slide rows, SHA-256 values, manifests, and representative tiles.
- Upgrade: open **Actions → Deploy production → Run workflow** on `main`. The
  protected `production` environment requires approval, deploys only the current
  reviewed `main` SHA, verifies readiness, and automatically restores the prior
  release if verification fails. The previous release remains under
  `/opt/pathlab-viewer.rollback-*` for manual rollback.

### One-click deployment setup

The workflow creates a temporary OCI Bastion managed SSH session for every
approved deployment and deletes it when the job exits. Administrator SSH remains
restricted to `admin_cidr`; the VM does not expose a deployment port to the
internet.

1. Enable the OCI Bastion agent plugin and create a Standard Bastion in the VM's
   VCN. Permit the Bastion private endpoint to reach target port 22.
2. Install `deploy/scripts/deploy-release.sh` as the root-owned executable
   `/usr/local/sbin/pathlab-viewer-deploy`.
3. Run `sudo deploy/scripts/configure-bastion-target.sh`. This creates the
   password-locked `pathlab-deploy` user, disables TTY and forwarding, and forces
   every session through the validated deployment script.
4. Give a dedicated OCI API user only the permissions required to create, read,
   and delete sessions for this Bastion. Do not use an administrator API key.
5. Configure the GitHub `production` environment with variables
   `OCI_BASTION_ID`, `OCI_INSTANCE_ID`, and `OCI_TARGET_PRIVATE_IP`, plus secrets
   `OCI_CONFIG`, `OCI_API_PRIVATE_KEY`, and `OCI_BASTION_KNOWN_HOSTS`.

`OCI_CONFIG` points `key_file` to `/home/runner/.oci/oci_api_key.pem`.
`OCI_BASTION_KNOWN_HOSTS` pins both the Bastion endpoint and target host keys.
Keep manual administrator SSH as the break-glass rollback path. The workflow
never reads or modifies `/srv/pathlab/data`.

Scope the API user's policy to the deployment Bastion, instance, and operating
system user. The session-management statement should constrain both the target
instance OCID and `target.bastion-session.username='pathlab-deploy'`; grant only
read access to instance, virtual-network, agent-plugin, and Bastion-session
metadata. The workflow does not need work-request permissions or permission to
manage the Bastion itself.

The US$1 monthly budget alert is a warning, not a spending cap. OCI public IPv4 policy and charges can change; verify the cost estimator and tenancy billing page at each deployment.

The currently reviewed live candidate is commit `0d94cc3`. Confirm the active release and readiness endpoints before upgrading or declaring production readiness.

## Administrator password recovery

Generate a single-use recovery code on the server with `docker compose -f deploy/compose.yaml exec api pathlab-admin issue-recovery-code --username admin`.

The code expires after 15 minutes and invalidates earlier unused codes. Enter it only at the HTTPS Forgot password form. The command prints the code once; do not place it in shell arguments, logs, screenshots, or tickets.

For console-only emergency reset, run `docker compose -f deploy/compose.yaml exec api pathlab-admin reset-password --username admin`. A password change or reset revokes every existing session and unused recovery code.
