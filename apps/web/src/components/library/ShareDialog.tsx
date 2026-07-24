import { Check, Copy, Link2, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import {
  ApiError,
  createLibraryShare,
  listLibraryShares,
  previewLibraryShare,
  revokeLibraryShare,
  rotateLibraryShare,
} from '../../api'
import type { LibraryShare, SharePreview } from '../../types'
import { LibraryDialog } from './LibraryDialog'

interface Props {
  open: boolean
  targetType: 'folder' | 'collection'
  targetId: string
  targetName: string
  onClose: () => void
}

export function ShareDialog({ open, targetType, targetId, targetName, onClose }: Props) {
  const [includeDescendants, setIncludeDescendants] = useState(false)
  const [autoIncludeNew, setAutoIncludeNew] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [expiresAt, setExpiresAt] = useState('')
  const [preview, setPreview] = useState<SharePreview | null>(null)
  const [share, setShare] = useState<LibraryShare | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [messageIsError, setMessageIsError] = useState(false)
  const [confirmRevoke, setConfirmRevoke] = useState(false)

  useEffect(() => {
    if (!open) return
    setIncludeDescendants(false)
    setAutoIncludeNew(false)
    setExpiresAt('')
    setConfirmed(false)
    setConfirmRevoke(false)
  }, [open, targetId, targetType])

  useEffect(() => {
    if (!open) return
    let active = true
    setMessage('')
    setMessageIsError(false)
    setConfirmed(false)
    setConfirmRevoke(false)
    setPreview(null)
    setShare(null)
    void Promise.all([
      previewLibraryShare(targetType, targetId, includeDescendants),
      listLibraryShares(),
    ]).then(([nextPreview, shares]) => {
      if (!active) return
      setPreview(nextPreview)
      setShare(shares.find((item) => item.targetType === targetType
        && item.targetId === targetId && item.state === 'active') ?? null)
    }).catch(() => {
      if (active) {
        setMessageIsError(true)
        setMessage('Unable to load the share preview.')
      }
    })
    return () => { active = false }
  }, [includeDescendants, open, targetId, targetType])

  const publicPath = useMemo(() => share
    ? `${targetType === 'folder' ? '/f/' : '/c/'}${share.publicId}`
    : '', [share, targetType])

  async function create() {
    if (!preview || !confirmed) return
    setBusy(true)
    setMessage('')
    setMessageIsError(false)
    try {
      setShare(await createLibraryShare({
        targetType,
        targetId,
        includeDescendants,
        autoIncludeNew,
        expiresAt: expiresAt ? new Date(expiresAt).toISOString() : null,
        slideIds: preview.included.map((item) => item.id),
        deidentifiedConfirmed: confirmed,
      }))
      setMessage('Shared link created.')
    } catch (caught) {
      setMessageIsError(true)
      setMessage(caught instanceof ApiError && caught.code === 'PRIVACY_SCANNER_REQUIRED'
        ? 'Multi-slide sharing stays disabled until the automated privacy scanner is available.'
        : 'Unable to create the shared link.')
    } finally {
      setBusy(false)
    }
  }

  async function copyLink() {
    setMessageIsError(false)
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${publicPath}`)
      setMessage('Link copied.')
    } catch {
      setMessageIsError(true)
      setMessage('Copy failed. Select and copy the link manually.')
    }
  }

  async function rotate() {
    if (!share) return
    setBusy(true)
    setMessage('')
    setMessageIsError(false)
    try {
      setShare(await rotateLibraryShare(share.id))
      setMessage('Link rotated. The previous link no longer works.')
    } catch {
      setMessageIsError(true)
      setMessage('Rotate failed. The current link is unchanged.')
    } finally { setBusy(false) }
  }

  async function revoke() {
    if (!share) return
    setBusy(true)
    setMessage('')
    setMessageIsError(false)
    try {
      await revokeLibraryShare(share.id)
      setShare(null)
      setConfirmRevoke(false)
      setMessage('Shared link revoked.')
    } catch {
      setMessageIsError(true)
      setMessage('Revoke failed. The current link remains active.')
    } finally { setBusy(false) }
  }

  return (
    <LibraryDialog open={open} title={`Share ${targetName}`} description={`${targetType === 'folder' ? 'Folder' : 'Collection'} sharing preview`} onClose={onClose}>
      <div className="share-dialog-content">
        {share ? <>
          <div className="share-active-summary"><Link2 /><div><strong>Active shared link</strong><span>{share.includedCount} slides · {share.expiresAt ? `expires ${new Date(share.expiresAt).toLocaleDateString()}` : 'no expiration'}</span></div></div>
          <input aria-label="Shared link" readOnly value={`${window.location.origin}${publicPath}`} />
          <div className="share-dialog-actions">
            <button type="button" onClick={() => void copyLink()}><Copy /> Copy link</button>
            <button type="button" disabled={busy} onClick={() => void rotate()}><RefreshCw /> Rotate</button>
            <button
              type="button"
              className="danger"
              disabled={busy}
              onClick={() => {
                if (confirmRevoke) void revoke()
                else setConfirmRevoke(true)
              }}
            >
              <Trash2 /> {confirmRevoke ? 'Confirm revoke' : 'Revoke'}
            </button>
          </div>
        </> : <>
          {targetType === 'folder' ? (
            <label className="share-check">
              <input className="share-checkbox-input" type="checkbox" checked={includeDescendants} onChange={(event) => setIncludeDescendants(event.target.checked)} />
              <span className="share-checkbox-indicator" aria-hidden="true"><Check /></span>
              <span>Include slides in descendant folders</span>
            </label>
          ) : null}
          <label className="share-check">
            <input className="share-checkbox-input" type="checkbox" checked={autoIncludeNew} onChange={(event) => setAutoIncludeNew(event.target.checked)} />
            <span className="share-checkbox-indicator" aria-hidden="true"><Check /></span>
            <span>Automatically include future additions</span>
            <small>Off by default. Routine moves never publish silently.</small>
          </label>
          {autoIncludeNew ? (
            <p className="share-auto-warning" role="status">
              Future additions can only publish after an explicit shared-destination warning.
            </p>
          ) : null}
          <label>Expiration (optional)<input type="datetime-local" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} /></label>
          <div className="share-preview-list">
            <strong>{preview?.included.length ?? 0} slides ready</strong>
            {preview?.included.slice(0, 6).map((item) => <span key={item.id}><Check /> {item.displayName}</span>)}
            {preview?.excluded.length ? <small>{preview.excluded.length} slides excluded because they are not ready or privacy-reviewed.</small> : null}
          </div>
          <label className="share-check privacy">
            <input className="share-checkbox-input" type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            <span className="share-checkbox-indicator" aria-hidden="true"><Check /></span>
            <ShieldCheck />
            <span>I confirm public names, teaching metadata, and visible pixels are de-identified.</span>
          </label>
          <button type="button" className="primary" disabled={busy || !confirmed || !preview?.included.length} onClick={() => void create()}>Create shared link</button>
        </>}
        {message ? <p role={messageIsError ? 'alert' : 'status'}>{message}</p> : null}
      </div>
    </LibraryDialog>
  )
}
