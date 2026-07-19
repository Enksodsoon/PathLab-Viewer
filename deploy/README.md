# OCI Always Free deployment

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
- Backup: `PATHLAB_BACKUP_DIR=/mnt/backup deploy/scripts/backup.sh`
- Restore drill: use a disposable VM and run `restore.sh --confirm /absolute/backup`, then compare slide rows, SHA-256 values, manifests, and representative tiles.
- Upgrade: fetch a reviewed commit and run `sudo systemctl reload pathlab-viewer`.

The US$1 monthly budget alert is a warning, not a spending cap. OCI public IPv4 policy and charges can change; verify the cost estimator and tenancy billing page at each deployment.

## Administrator password recovery

Generate a single-use recovery code on the server with `docker compose -f deploy/compose.yaml exec api pathlab-admin issue-recovery-code --username admin`.

The code expires after 15 minutes and invalidates earlier unused codes. Enter it only at the HTTPS Forgot password form. The command prints the code once; do not place it in shell arguments, logs, screenshots, or tickets.

For console-only emergency reset, run `docker compose -f deploy/compose.yaml exec api pathlab-admin reset-password --username admin`. A password change or reset revokes every existing session and unused recovery code.
