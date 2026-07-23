from __future__ import annotations

from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}")
    write(path, content.replace(old, new, 1))


write(
    "server/wsi_viewer/config.py",
    dedent(
        '''\
        from pathlib import Path
        from typing import Literal, Self

        from pydantic import PositiveInt, model_validator
        from pydantic_settings import BaseSettings, SettingsConfigDict


        PRODUCTION_SECRET_PLACEHOLDERS = {
            "change-this-before-deployment",
            "replace-with-at-least-32-random-bytes",
            "generate-with-openssl-rand-hex-32",
        }


        class Settings(BaseSettings):
            model_config = SettingsConfigDict(
                env_prefix="PATHLAB_",
                env_file=".env",
                extra="ignore",
            )

            environment: Literal["development", "test", "production"] = "development"
            database_url: str = "sqlite:///./var/pathlab.sqlite3"
            data_root: Path = Path("./var/data")
            secret_key: str = "change-this-before-deployment"
            secure_cookies: bool = True
            session_hours: int = 12
            max_upload_bytes: int = 5 * 1024**3
            storage_cap_bytes: int = 120 * 1024**3
            tus_public_url: str = "/api/v1/uploads/"
            tus_internal_upload_dir: Path = Path("./var/tus")
            worker_stale_seconds: int = 300
            serve_public_tiles: bool = False
            libvips_concurrency: PositiveInt = 1
            libvips_cache_max_mem_bytes: PositiveInt = 256 * 1024**2
            libvips_cache_max_files: PositiveInt = 128
            libvips_cache_max_operations: PositiveInt = 100
            multi_share_enabled: bool = False

            @model_validator(mode="after")
            def validate_production_security(self) -> Self:
                if self.environment != "production":
                    return self
                secret = self.secret_key.strip()
                if (
                    len(secret.encode("utf-8")) < 32
                    or secret.casefold() in PRODUCTION_SECRET_PLACEHOLDERS
                ):
                    raise ValueError("Production requires a unique secret key of at least 32 bytes")
                if not self.secure_cookies:
                    raise ValueError("Production requires secure cookies")
                return self
        '''
    ),
)

replace_once(
    "server/wsi_viewer/main.py",
    dedent(
        '''\
        class UploadCompleteRequest(BaseModel):
            token: str
            path: Path
            length: int = Field(gt=0)
        '''
    ),
    dedent(
        '''\
        class PublishRequest(BaseModel):
            model_config = ConfigDict(populate_by_name=True)

            deidentified_confirmed: bool = Field(alias="deidentifiedConfirmed")


        class UploadCompleteRequest(BaseModel):
            token: str
            path: Path
            length: int = Field(gt=0)
        '''
    ),
)

replace_once(
    "server/wsi_viewer/main.py",
    dedent(
        '''\
        def _slide_json(slide: Slide, *, public: bool = False) -> dict[str, Any]:
            result: dict[str, Any] = {
        '''
    ),
    dedent(
        '''\
        def _public_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
            if not metadata:
                return None
            allowed = ("width", "height", "physicalSizeX")
            return {key: metadata[key] for key in allowed if metadata.get(key) is not None}


        def _slide_json(slide: Slide, *, public: bool = False) -> dict[str, Any]:
            result: dict[str, Any] = {
        '''
    ),
)

replace_once(
    "server/wsi_viewer/main.py",
    dedent(
        '''\
            if public:
                result.pop("id")
                result.pop("sourceBytes")
                result.pop("errorCode")
                result.pop("errorMessage")
                result["tileSource"] = f"/tiles/{slide.public_id}/slide.dzi"
        '''
    ),
    dedent(
        '''\
            if public:
                result.pop("id")
                result.pop("sourceBytes")
                result.pop("errorCode")
                result.pop("errorMessage")
                result["metadata"] = _public_metadata(slide.slide_metadata)
                result["tileSource"] = f"/tiles/{slide.public_id}/slide.dzi"
        '''
    ),
)

replace_once(
    "server/wsi_viewer/main.py",
    dedent(
        '''\
            @app.post("/api/v1/admin/slides/{slide_id}/publish")
            def publish(slide_id: str, authenticated: CsrfSession, db: Database) -> dict[str, Any]:
                slide = db.get(Slide, slide_id)
                if slide is None:
                    raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
                try:
                    ensure_grant(db, storage, slide, INDIVIDUAL, slide.id)
        '''
    ),
    dedent(
        '''\
            @app.post("/api/v1/admin/slides/{slide_id}/publish")
            def publish(
                slide_id: str,
                authenticated: CsrfSession,
                db: Database,
                payload: PublishRequest | None = None,
            ) -> dict[str, Any]:
                if payload is None or not payload.deidentified_confirmed:
                    raise HTTPException(
                        status_code=422,
                        detail={"code": "DEIDENTIFICATION_CONFIRMATION_REQUIRED"},
                    )
                slide = db.get(Slide, slide_id)
                if slide is None:
                    raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
                slide.privacy_status = "passed"
                slide.privacy_scanned_at = datetime.now(UTC).replace(tzinfo=None)
                try:
                    ensure_grant(db, storage, slide, INDIVIDUAL, slide.id)
        '''
    ),
)

replace_once(
    "server/wsi_viewer/main.py",
    "select(Slide).where(Slide.public_id == public_id, Slide.state == SlideState.PUBLISHED)",
    dedent(
        '''\
        select(Slide).where(
                    Slide.public_id == public_id,
                    Slide.state == SlideState.PUBLISHED,
                    Slide.privacy_status == "passed",
                )
        '''
    ).strip(),
)

replace_once(
    "server/wsi_viewer/publication.py",
    dedent(
        '''\
            database.add(grant)
            slide.state = SlideState.PUBLISHED
            slide.published_at = datetime.now(UTC).replace(tzinfo=None)
        '''
    ),
    dedent(
        '''\
            database.add(grant)
            now = datetime.now(UTC).replace(tzinfo=None)
            slide.privacy_status = "passed"
            slide.privacy_scanned_at = now
            slide.state = SlideState.PUBLISHED
            slide.published_at = now
        '''
    ),
)

replace_once(
    "server/wsi_viewer/library_routes.py",
    dedent(
        '''\
        def _get_collection(database: OrmSession, collection_id: str) -> Collection:
            collection = database.get(Collection, collection_id)
            if collection is None:
                raise HTTPException(status_code=404, detail={"code": "COLLECTION_NOT_FOUND"})
            return collection
        '''
    ),
    dedent(
        '''\
        def _get_collection(database: OrmSession, collection_id: str) -> Collection:
            collection = database.get(Collection, collection_id)
            if collection is None:
                raise HTTPException(status_code=404, detail={"code": "COLLECTION_NOT_FOUND"})
            return collection


        def _has_active_share(
            database: OrmSession,
            *,
            target_type: str,
            target_id: str,
        ) -> bool:
            return database.scalar(
                select(LibraryShare.id)
                .where(
                    LibraryShare.target_type == target_type,
                    LibraryShare.target_id == target_id,
                    LibraryShare.is_active.is_(True),
                    LibraryShare.revoked_at.is_(None),
                )
                .limit(1)
            ) is not None
        '''
    ),
)

replace_once(
    "server/wsi_viewer/library_routes.py",
    dedent(
        '''\
            folder = database.get(Folder, folder_id)
            if folder is None or folder.trashed_at is not None:
                raise HTTPException(status_code=404, detail={"code": "FOLDER_NOT_FOUND"})
            try:
                if "parent_id" in payload.model_fields_set:
        '''
    ),
    dedent(
        '''\
            folder = database.get(Folder, folder_id)
            if folder is None or folder.trashed_at is not None:
                raise HTTPException(status_code=404, detail={"code": "FOLDER_NOT_FOUND"})
            if (
                payload.name is not None or payload.description is not None
            ) and _has_active_share(
                database,
                target_type="folder",
                target_id=folder.id,
            ):
                raise HTTPException(status_code=409, detail={"code": "SHARE_ACTIVE"})
            try:
                if "parent_id" in payload.model_fields_set:
        '''
    ),
)

replace_once(
    "server/wsi_viewer/library_routes.py",
    dedent(
        '''\
            collection = _get_collection(database, collection_id)
            try:
                if payload.name is not None:
        '''
    ),
    dedent(
        '''\
            collection = _get_collection(database, collection_id)
            if (
                payload.name is not None or payload.description is not None
            ) and _has_active_share(
                database,
                target_type="collection",
                target_id=collection.id,
            ):
                raise HTTPException(status_code=409, detail={"code": "SHARE_ACTIVE"})
            try:
                if payload.name is not None:
        '''
    ),
)

replace_once(
    "server/wsi_viewer/library_routes.py",
    dedent(
        '''\
                fields = {
                    "display_name": payload.display_name,
                    "description": payload.description,
                    "case_id": payload.case_id,
                    "organ_site": payload.organ_site,
                    "stain": payload.stain,
                    "diagnosis": payload.diagnosis,
                    "course": payload.course,
                    "tags": payload.tags,
                    "teaching_note": payload.teaching_note,
                    "admin_notes": payload.admin_notes,
                }
                for slide in slides:
                    for field, value in fields.items():
                        if value is not None:
                            setattr(slide, field, value)
                database.commit()
        '''
    ),
    dedent(
        '''\
                public_fields = {
                    "display_name": payload.display_name,
                    "description": payload.description,
                    "case_id": payload.case_id,
                    "organ_site": payload.organ_site,
                    "stain": payload.stain,
                    "diagnosis": payload.diagnosis,
                    "course": payload.course,
                    "tags": payload.tags,
                    "teaching_note": payload.teaching_note,
                }
                public_changes = {
                    field: value for field, value in public_fields.items() if value is not None
                }
                if public_changes:
                    shared = database.scalar(
                        select(PublicationGrant.id)
                        .where(PublicationGrant.slide_id.in_(slide_ids))
                        .limit(1)
                    )
                    if shared is not None:
                        raise HTTPException(status_code=409, detail={"code": "SLIDE_PUBLIC"})
                fields = {**public_fields, "admin_notes": payload.admin_notes}
                for slide in slides:
                    for field, value in fields.items():
                        if value is not None:
                            setattr(slide, field, value)
                    if public_changes:
                        slide.privacy_status = "pending"
                        slide.privacy_scanned_at = None
                database.commit()
        '''
    ),
)

replace_once(
    "apps/web/src/api.ts",
    dedent(
        '''\
        export async function deleteSlide(id: string): Promise<void> {
        '''
    ),
    dedent(
        '''\
        export async function publishSlide(id: string): Promise<AdminSlide> {
          return json<AdminSlide>(
            await fetch(`/api/v1/admin/slides/${encodeURIComponent(id)}/publish`, {
              method: 'POST',
              credentials: 'same-origin',
              headers: csrfHeaders(true),
              body: JSON.stringify({ deidentifiedConfirmed: true }),
            }),
          )
        }

        export async function deleteSlide(id: string): Promise<void> {
        '''
    ),
)

write(
    "apps/web/src/components/library/PublishConfirmationDialog.tsx",
    dedent(
        '''\
        import { useEffect, useState } from 'react'

        import { LibraryDialog } from './LibraryDialog'

        interface PublishConfirmationDialogProps {
          open: boolean
          count: number
          busy: boolean
          onClose: () => void
          onConfirm: () => void
        }

        export function PublishConfirmationDialog({
          open,
          count,
          busy,
          onClose,
          onConfirm,
        }: PublishConfirmationDialogProps) {
          const [confirmed, setConfirmed] = useState(false)

          useEffect(() => {
            if (open) setConfirmed(false)
          }, [open])

          const label = `Publish ${count} slide${count === 1 ? '' : 's'}`
          return (
            <LibraryDialog
              open={open}
              title="Confirm deidentification"
              description="Published slides and their public teaching details can be opened by anyone with the link."
              onClose={() => { if (!busy) onClose() }}
            >
              <div className="library-dialog-form">
                <label className="privacy-confirmation">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    disabled={busy}
                    onChange={(event) => setConfirmed(event.target.checked)}
                  />
                  Patient identifiers and private information have been removed from the image,
                  display name, diagnosis, teaching note, and other public fields.
                </label>
                <p>Administrator notes and the original filename remain private.</p>
                <button
                  type="button"
                  className="primary"
                  disabled={!confirmed || busy || count < 1}
                  onClick={onConfirm}
                >
                  {busy ? 'Publishing…' : label}
                </button>
              </div>
            </LibraryDialog>
          )
        }
        '''
    ),
)

replace_once(
    "apps/web/src/pages/AdminPage.tsx",
    "  mutateSlide,\n  reserveUpload,",
    "  mutateSlide,\n  publishSlide,\n  reserveUpload,",
)
replace_once(
    "apps/web/src/pages/AdminPage.tsx",
    "import { ShareDialog } from '../components/library/ShareDialog'",
    "import { PublishConfirmationDialog } from '../components/library/PublishConfirmationDialog'\nimport { ShareDialog } from '../components/library/ShareDialog'",
)
replace_once(
    "apps/web/src/pages/AdminPage.tsx",
    "  | 'share'\n  | null",
    "  | 'publish'\n  | 'share'\n  | null",
)
replace_once(
    "apps/web/src/pages/AdminPage.tsx",
    "  const [signingOut, setSigningOut] = useState(false)",
    "  const [signingOut, setSigningOut] = useState(false)\n  const [publishBusy, setPublishBusy] = useState(false)",
)
replace_once(
    "apps/web/src/pages/AdminPage.tsx",
    dedent(
        '''\
              if (action === 'move') setDialog('move')
              else if (action === 'collection') setDialog('add-collection')
              else if (action === 'delete') setDialog('delete')
              else if (action === 'publish' || action === 'unpublish' || action === 'retry') {
                const changed = await mutateSlide(slide.id, action)
        '''
    ),
    dedent(
        '''\
              if (action === 'move') setDialog('move')
              else if (action === 'collection') setDialog('add-collection')
              else if (action === 'delete') setDialog('delete')
              else if (action === 'publish') {
                setDialog('publish')
                return
              } else if (action === 'unpublish' || action === 'retry') {
                const changed = await mutateSlide(slide.id, action)
        '''
    ),
)
replace_once(
    "apps/web/src/pages/AdminPage.tsx",
    "      eligible.map((slide) => mutateSlide(slide.id, action)),",
    "      eligible.map((slide) => action === 'publish'\n        ? publishSlide(slide.id)\n        : mutateSlide(slide.id, action)),",
)
replace_once(
    "apps/web/src/pages/AdminPage.tsx",
    "          onPublish={() => runAction(publishSelected, 'Publish')}",
    "          onPublish={() => openNamedDialog('publish')}",
)
replace_once(
    "apps/web/src/pages/AdminPage.tsx",
    dedent(
        '''\
              <LibraryDialog
                open={dialog === 'upload'}
        '''
    ),
    dedent(
        '''\
              <PublishConfirmationDialog
                open={dialog === 'publish'}
                count={selected.size}
                busy={publishBusy}
                onClose={() => setDialog(null)}
                onConfirm={() => {
                  if (publishBusy) return
                  setPublishBusy(true)
                  setError('')
                  void publishSelected()
                    .then(() => setDialog(null))
                    .catch(() => setError('Publish failed. Review deidentification and try again.'))
                    .finally(() => setPublishBusy(false))
                }}
              />

              <LibraryDialog
                open={dialog === 'upload'}
        '''
    ),
)

replace_once(
    "tests/backend/test_api.py",
    dedent(
        '''\
                published = client.post(
                    f"/api/v1/admin/slides/{slide_id}/publish", headers={"X-CSRF-Token": csrf}
                )
        '''
    ),
    dedent(
        '''\
                published = client.post(
                    f"/api/v1/admin/slides/{slide_id}/publish",
                    headers={"X-CSRF-Token": csrf},
                    json={"deidentifiedConfirmed": True},
                )
        '''
    ),
)

replace_once(
    "apps/web/src/test/library-explorer.test.tsx",
    "  mutateSlide: vi.fn(),\n  deleteLibrarySlide: vi.fn(),",
    "  mutateSlide: vi.fn(),\n  publishSlide: vi.fn(),\n  deleteLibrarySlide: vi.fn(),",
)
replace_once(
    "apps/web/src/test/library-explorer.test.tsx",
    dedent(
        '''\
          api.mutateSlide.mockImplementation(async (id, action) => ({
            ...items.items.find((slide) => slide.id === id),
            state: action === 'unpublish' ? 'ready_private' : action === 'retry' ? 'queued' : 'published',
          }))
        '''
    ),
    dedent(
        '''\
          api.mutateSlide.mockImplementation(async (id, action) => ({
            ...items.items.find((slide) => slide.id === id),
            state: action === 'unpublish' ? 'ready_private' : action === 'retry' ? 'queued' : 'published',
          }))
          api.publishSlide.mockImplementation(async (id) => ({
            ...items.items.find((slide) => slide.id === id),
            state: 'published',
          }))
        '''
    ),
)
replace_once(
    "apps/web/src/test/library-explorer.test.tsx",
    dedent(
        '''\
          it('keeps failed mutations visible instead of leaving a dead control', async () => {
            api.mutateSlide.mockRejectedValueOnce(new Error('offline'))
            render(<AdminPage />, { wrapper: MemoryRouter })
            await screen.findAllByText('Colon adenocarcinoma')

            await userEvent.click(screen.getByRole('button', {
              name: /more actions for colon adenocarcinoma/i,
            }))
            await userEvent.click(screen.getByRole('menuitem', { name: /^publish$/i }))

            expect(await screen.findByRole('alert')).toHaveTextContent(/publish.*failed/i)
            expect(screen.getByRole('button', {
              name: /more actions for colon adenocarcinoma/i,
            })).toBeEnabled()
          })
        '''
    ),
    dedent(
        '''\
          it('keeps failed mutations visible instead of leaving a dead control', async () => {
            api.publishSlide.mockRejectedValueOnce(new Error('offline'))
            render(<AdminPage />, { wrapper: MemoryRouter })
            await screen.findAllByText('Colon adenocarcinoma')

            await userEvent.click(screen.getByRole('button', {
              name: /more actions for colon adenocarcinoma/i,
            }))
            await userEvent.click(screen.getByRole('menuitem', { name: /^publish$/i }))
            await userEvent.click(screen.getByRole('checkbox', {
              name: /patient identifiers and private information have been removed/i,
            }))
            await userEvent.click(screen.getByRole('button', { name: /publish 1 slide/i }))

            expect(await screen.findByRole('alert')).toHaveTextContent(/publish.*failed/i)
            expect(screen.getByRole('button', {
              name: /more actions for colon adenocarcinoma/i,
            })).toBeEnabled()
          })
        '''
    ),
)

replace_once(
    "tests/backend/test_public_hardening.py",
    '    assert "deployments: write" not in workflow\n',
    '    assert "url: https://" not in workflow\n',
)

write(
    "deploy/Caddyfile",
    dedent(
        '''\
        {
        \temail {$ACME_EMAIL}
        \tmetrics
        }

        {$DOMAIN} {
        \tencode zstd gzip

        \theader {
        \t\tContent-Security-Policy "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self' data:; worker-src 'self' blob:"
        \t\tStrict-Transport-Security "max-age=31536000; includeSubDomains"
        \t\tReferrer-Policy "no-referrer"
        \t\tX-Content-Type-Options "nosniff"
        \t\tX-Frame-Options "DENY"
        \t\tX-Robots-Tag "noindex, nofollow, noarchive"
        \t\tPermissions-Policy "camera=(), microphone=(), geolocation=()"
        \t\tCross-Origin-Opener-Policy "same-origin"
        \t\tCross-Origin-Resource-Policy "same-origin"
        \t\t-Server
        \t}

        \t@internal_api path /api/v1/internal/*
        \trespond @internal_api 404

        \t@uploads path /api/v1/uploads/*
        \thandle @uploads {
        \t\theader Cache-Control "no-store"
        \t\treverse_proxy tusd:8080
        \t}

        \t@backend path /api/* /livez /readyz
        \thandle @backend {
        \t\theader Cache-Control "no-store"
        \t\treverse_proxy api:8000
        \t}

        \thandle_path /tiles/* {
        \t\troot * /pathlab-data/public
        \t\theader Cache-Control "public, max-age=31536000, s-maxage=60, immutable"
        \t\theader X-Content-Type-Options "nosniff"
        \t\tfile_server
        \t}

        \thandle /assets/* {
        \t\troot * /srv
        \t\theader Cache-Control "public, max-age=31536000, immutable"
        \t\tfile_server
        \t}

        \thandle {
        \t\troot * /srv
        \t\theader Cache-Control "no-cache"
        \t\ttry_files {path} /index.html
        \t\tfile_server
        \t}
        }
        '''
    ),
)

replace_once(
    "deploy/scripts/deploy-release.sh",
    'HEALTH_URL="https://pathlab-viewer.140-245-126-212.sslip.io/readyz"\n',
    "",
)
replace_once(
    "deploy/scripts/deploy-release.sh",
    dedent(
        '''\
        [[ -f "${LIVE_DIR}/deploy/.env" ]] || fail "live deploy/.env is missing"

        TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
        '''
    ),
    dedent(
        '''\
        [[ -f "${LIVE_DIR}/deploy/.env" ]] || fail "live deploy/.env is missing"
        DOMAIN="$(sed -n 's/^DOMAIN=//p' "${LIVE_DIR}/deploy/.env" | tail -n 1)"
        DOMAIN="${DOMAIN%\\\"}"
        DOMAIN="${DOMAIN#\\\"}"
        DOMAIN="${DOMAIN%\\'}"
        DOMAIN="${DOMAIN#\\'}"
        [[ "${DOMAIN}" =~ ^[A-Za-z0-9.-]+$ ]] || fail "DOMAIN is missing or invalid"
        HEALTH_URL="https://${DOMAIN}/readyz"

        TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
        '''
    ),
)

write(
    ".github/workflows/deploy-production.yml",
    dedent(
        '''\
        name: Deploy production

        on:
          workflow_dispatch:

        permissions:
          contents: read
          checks: read
          deployments: write

        concurrency:
          group: production-deploy
          cancel-in-progress: false

        jobs:
          deploy:
            if: github.ref == 'refs/heads/main'
            runs-on: ubuntu-24.04
            environment:
              name: production
            steps:
              - uses: actions/checkout@v4
                with:
                  ref: main
                  persist-credentials: false

              - uses: actions/setup-python@v5
                with:
                  python-version: "3.12"

              - name: Require successful CI checks
                env:
                  GH_TOKEN: ${{ github.token }}
                run: |
                  for check in backend web containers; do
                    conclusion="$(gh api "repos/${GITHUB_REPOSITORY}/commits/${GITHUB_SHA}/check-runs" \\
                      --jq ".check_runs[] | select(.name == \\\"${check}\\\") | .conclusion" | head -n 1)"
                    test "${conclusion}" = success || {
                      echo "Required check ${check} is ${conclusion:-missing}, not successful."
                      exit 1
                    }
                  done

              - name: Install OCI CLI
                run: pip install oci-cli==3.89.2

              - name: Configure OCI and pinned SSH identities
                env:
                  OCI_CONFIG: ${{ secrets.OCI_CONFIG }}
                  OCI_API_PRIVATE_KEY: ${{ secrets.OCI_API_PRIVATE_KEY }}
                  OCI_BASTION_KNOWN_HOSTS: ${{ secrets.OCI_BASTION_KNOWN_HOSTS }}
                run: |
                  install -d -m 700 ~/.oci
                  install -m 600 /dev/null ~/.oci/config
                  install -m 600 /dev/null ~/.oci/oci_api_key.pem
                  printf '%s\n' "${OCI_CONFIG}" > ~/.oci/config
                  printf '%s\n' "${OCI_API_PRIVATE_KEY}" > ~/.oci/oci_api_key.pem
                  install -d -m 700 ~/.ssh
                  printf '%s\n' "${OCI_BASTION_KNOWN_HOSTS}" > ~/.ssh/known_hosts
                  chmod 600 ~/.ssh/known_hosts

              - name: Deploy through temporary OCI Bastion session
                env:
                  OCI_BASTION_ID: ${{ vars.OCI_BASTION_ID }}
                  OCI_INSTANCE_ID: ${{ vars.OCI_INSTANCE_ID }}
                  OCI_TARGET_PRIVATE_IP: ${{ vars.OCI_TARGET_PRIVATE_IP }}
                  OCI_TARGET_USER: pathlab-deploy
                  OCI_KNOWN_HOSTS_FILE: /home/runner/.ssh/known_hosts
                run: deploy/scripts/deploy-via-bastion.sh "$GITHUB_SHA"

              - name: Remove temporary cloud credentials
                if: always()
                run: rm -rf -- ~/.oci ~/.ssh

              - name: Record deployment result
                run: |
                  {
                    echo "## Production deployment"
                    echo ""
                    echo "- Commit: `${GITHUB_SHA}`"
                    echo "- Result: deployed and health-checked"
                  } >> "${GITHUB_STEP_SUMMARY}"
        '''
    ),
)

replace_once(
    "deploy/scripts/deploy-via-bastion.sh",
    '      echo "Warning: Bastion session cleanup must be checked manually: ${SESSION_ID}" >&2\n',
    '      echo "Warning: Bastion session cleanup must be checked manually." >&2\n',
)

replace_once(
    "deploy/compose.yaml",
    "      PATHLAB_DATABASE_URL: sqlite:////data/db/pathlab.sqlite3\n",
    "      PATHLAB_ENVIRONMENT: production\n      PATHLAB_DATABASE_URL: sqlite:////data/db/pathlab.sqlite3\n",
)
replace_once(
    "deploy/compose.yaml",
    "      PATHLAB_DATABASE_URL: sqlite:////data/db/pathlab.sqlite3\n",
    "      PATHLAB_ENVIRONMENT: production\n      PATHLAB_DATABASE_URL: sqlite:////data/db/pathlab.sqlite3\n",
)

replace_once(
    ".env.example",
    "PATHLAB_DATABASE_URL=sqlite:///./var/pathlab.sqlite3\n",
    "PATHLAB_ENVIRONMENT=development\nPATHLAB_DATABASE_URL=sqlite:///./var/pathlab.sqlite3\n",
)

ci = read(".github/workflows/ci.yml")
ci = ci.replace(
    "      - uses: actions/checkout@v4\n",
    "      - uses: actions/checkout@v4\n        with:\n          persist-credentials: false\n",
)
if ci.count("persist-credentials: false") != 3:
    raise RuntimeError("CI checkout hardening did not affect all three jobs")
write(".github/workflows/ci.yml", ci)

write(
    "scripts/check_public_repository.py",
    dedent(
        '''\
        #!/usr/bin/env python3
        from __future__ import annotations

        import ipaddress
        import re
        import subprocess
        import sys
        from pathlib import Path


        ROOT = Path(__file__).resolve().parents[1]
        SELF = Path(__file__).resolve()
        TEXT_SUFFIXES = {
            "", ".caddyfile", ".css", ".env", ".html", ".ini", ".js", ".json",
            ".jsx", ".md", ".mjs", ".py", ".sh", ".toml", ".ts", ".tsx",
            ".txt", ".yaml", ".yml",
        }
        PRIVATE_KEY_MARKERS = (
            "-----BEGIN PRIVATE KEY-----",
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN OPENSSH PRIVATE KEY-----",
            "-----BEGIN EC PRIVATE KEY-----",
        )
        TOKEN_PATTERNS = (
            re.compile(r"\\bgh[pousr]_[A-Za-z0-9_]{30,}\\b"),
            re.compile(r"\\bgithub_pat_[A-Za-z0-9_]{40,}\\b"),
            re.compile(r"\\bAKIA[0-9A-Z]{16}\\b"),
            re.compile(r"\\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\\b"),
        )
        EMAIL_PATTERN = re.compile(r"(?<![\\w.+-])([\\w.+-]+)@([A-Za-z0-9.-]+\\.[A-Za-z]{2,})(?![\\w.-])")
        IPV4_PATTERN = re.compile(r"(?<![0-9])(?:[0-9]{1,3}\\.){3}[0-9]{1,3}(?![0-9])")
        DYNAMIC_DNS_PATTERN = re.compile(r"\\b(?:[0-9]{1,3}[-.]){3}[0-9]{1,3}\\.(?:sslip|nip)\\.io\\b", re.I)
        ALLOWED_EMAIL_DOMAINS = {
            "example.com", "example.net", "example.org", "example.test", "users.noreply.github.com",
        }
        LOCK_NAMES = {"pnpm-lock.yaml", "package-lock.json", "yarn.lock"}


        def tracked_files() -> list[Path]:
            result = subprocess.run(
                ["git", "ls-files", "-z"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )
            return [ROOT / item.decode() for item in result.stdout.split(b"\\0") if item]


        def is_public_ip(value: str) -> bool:
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                return False
            return not (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_multicast
                or address.is_reserved
                or address.is_unspecified
            )


        def main() -> int:
            findings: list[tuple[str, int, str]] = []
            for path in tracked_files():
                relative = path.relative_to(ROOT).as_posix()
                if path.resolve() == SELF:
                    continue
                if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
                    findings.append((relative, 1, "committed environment file"))
                    continue
                if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Caddyfile", "Dockerfile"}:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for line_number, line in enumerate(text.splitlines(), start=1):
                    if any(marker in line for marker in PRIVATE_KEY_MARKERS):
                        findings.append((relative, line_number, "private key material"))
                    if any(pattern.search(line) for pattern in TOKEN_PATTERNS):
                        findings.append((relative, line_number, "credential-like token"))
                    if DYNAMIC_DNS_PATTERN.search(line):
                        findings.append((relative, line_number, "IP-derived public hostname"))
                    for _, domain in EMAIL_PATTERN.findall(line):
                        if domain.casefold() not in ALLOWED_EMAIL_DOMAINS:
                            findings.append((relative, line_number, "non-example email address"))
                    if path.name not in LOCK_NAMES:
                        for candidate in IPV4_PATTERN.findall(line):
                            if is_public_ip(candidate):
                                findings.append((relative, line_number, "public IP address"))
            if findings:
                for path, line, category in sorted(set(findings)):
                    print(f"{path}:{line}: {category}", file=sys.stderr)
                print("Public repository check failed.", file=sys.stderr)
                return 1
            print("Public repository check passed.")
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        '''
    ),
)

write(
    ".github/workflows/security.yml",
    dedent(
        '''\
        name: Security

        on:
          push:
            branches: [main]
          pull_request:
          schedule:
            - cron: "17 3 * * 1"

        concurrency:
          group: security-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
          cancel-in-progress: true

        permissions:
          contents: read

        jobs:
          repository-and-dependencies:
            runs-on: ubuntu-24.04
            steps:
              - uses: actions/checkout@v4
                with:
                  persist-credentials: false
              - uses: actions/setup-python@v5
                with:
                  python-version: "3.12"
              - name: Check public repository content
                run: python scripts/check_public_repository.py
              - name: Audit Python dependencies
                run: |
                  python -m pip install --upgrade pip pip-audit
                  pip-audit --strict --progress-spinner off .
              - uses: pnpm/action-setup@v4
                with:
                  version: "11.9.0"
              - uses: actions/setup-node@v4
                with:
                  node-version: "24.14.0"
                  cache: pnpm
              - run: pnpm install --frozen-lockfile
              - name: Audit JavaScript dependencies
                run: pnpm audit --audit-level high

          codeql:
            name: CodeQL (${{ matrix.language }})
            runs-on: ubuntu-24.04
            permissions:
              contents: read
              security-events: write
            strategy:
              fail-fast: false
              matrix:
                language: [python, javascript-typescript]
            steps:
              - uses: actions/checkout@v4
                with:
                  persist-credentials: false
              - uses: github/codeql-action/init@v4
                with:
                  languages: ${{ matrix.language }}
                  build-mode: none
              - uses: github/codeql-action/analyze@v4
        '''
    ),
)

write(
    ".github/dependabot.yml",
    dedent(
        '''\
        version: 2
        updates:
          - package-ecosystem: pip
            directory: /
            schedule:
              interval: weekly
            groups:
              python-dependencies:
                patterns: ["*"]
          - package-ecosystem: npm
            directory: /
            schedule:
              interval: weekly
            groups:
              web-dependencies:
                patterns: ["*"]
          - package-ecosystem: github-actions
            directory: /
            schedule:
              interval: weekly
            groups:
              actions:
                patterns: ["*"]
          - package-ecosystem: docker
            directory: /deploy
            schedule:
              interval: weekly
            groups:
              containers:
                patterns: ["*"]
        '''
    ),
)

replace_once(
    "SECURITY.md",
    "## Security boundaries\n",
    dedent(
        '''\
        ## Automated safeguards

        Pull requests run current-tree disclosure checks, Python and JavaScript dependency audits,
        and CodeQL analysis. Production configuration refuses placeholder secrets or insecure cookies.
        Publication requires an explicit deidentification confirmation, and public responses expose
        only the technical image fields needed by the viewer.

        ## Security boundaries
        '''
    ),
)

replace_once(
    "README.md",
    "## Security and privacy\n",
    dedent(
        '''\
        ## Public-repository safeguards

        - Production configuration fails closed unless a unique secret and secure cookies are set.
        - Deployment endpoints and infrastructure addresses are supplied through protected settings,
          not committed source files.
        - Internal upload hook routes are blocked at the public reverse proxy.
        - Publishing requires explicit confirmation that image and public teaching fields are deidentified.
        - CI checks the current tree for common secret and infrastructure disclosures, audits dependencies,
          and runs CodeQL.

        ## Security and privacy
        '''
    ),
)

# Remove this one-time automation from the final branch tree.
(ROOT / ".github/workflows/apply-public-hardening.yml").unlink(missing_ok=True)
Path(__file__).unlink(missing_ok=True)
