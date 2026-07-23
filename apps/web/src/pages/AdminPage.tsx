import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, CircleAlert, CloudUpload, Copy, Eye, KeyRound, LogOut, RefreshCw, Trash2 } from 'lucide-react'

import { ApiError, deleteSlide, listSlides, logout, mutateSlide, reserveUpload } from '../api'
import { AccountSecurityDialog, AuthPanel } from '../components/AuthPanels'
import { Brand } from '../components/Brand'
import { DeleteSlideDialog } from '../components/DeleteSlideDialog'
import { PublishSlideDialog } from '../components/PublishSlideDialog'
import type { AdminSlide, SlideState } from '../types'
import { startTusUpload } from '../upload'

const LABELS: Record<SlideState, string> = {
  uploading: 'Uploading',
  queued: 'Queued',
  validating: 'Validating',
  converting: 'Converting',
  ready_private: 'Ready — private',
  published: 'Published',
  failed: 'Failed',
  deleting: 'Deleting',
}

const ACTIVE_STATES = new Set<SlideState>([
  'uploading',
  'queued',
  'validating',
  'converting',
  'deleting',
])

function formatBytes(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

function uploadStartErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 413) {
    return 'The file is too large or there is not enough available storage.'
  }
  return 'Upload could not start. Check the file and try again.'
}

export function AdminPage() {
  const [slides, setSlides] = useState<AdminSlide[]>([])
  const [authorized, setAuthorized] = useState<boolean | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [progress, setProgress] = useState<number | null>(null)
  const [notice, setNotice] = useState('')
  const [securityOpen, setSecurityOpen] = useState(false)
  const [slidePendingPublication, setSlidePendingPublication] = useState<AdminSlide | null>(null)
  const [slidePendingDeletion, setSlidePendingDeletion] = useState<AdminSlide | null>(null)
  const [authNotice, setAuthNotice] = useState('')
  const [signingOut, setSigningOut] = useState(false)
  const [logoutError, setLogoutError] = useState('')
  const [isVisible, setIsVisible] = useState(() => document.visibilityState !== 'hidden')
  const fileInput = useRef<HTMLInputElement>(null)
  const authEpoch = useRef(0)

  const refresh = useCallback(async () => {
    const epoch = authEpoch.current
    try {
      const nextSlides = await listSlides()
      if (epoch !== authEpoch.current) return
      setSlides(nextSlides)
      setAuthorized(true)
    } catch (error) {
      if (epoch !== authEpoch.current) return
      if (error instanceof ApiError && error.status === 401) {
        authEpoch.current += 1
        setSlides([])
        setAuthorized(false)
      }
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (!authorized) return
    const handleVisibilityChange = () => {
      const nextVisible = document.visibilityState !== 'hidden'
      setIsVisible(nextVisible)
      if (nextVisible) void refresh()
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [authorized, refresh])

  const hasActiveSlides = useMemo(
    () => slides.some((slide) => ACTIVE_STATES.has(slide.state)),
    [slides],
  )

  useEffect(() => {
    if (!authorized || !hasActiveSlides || !isVisible) return
    const timer = window.setInterval(() => void refresh(), 4000)
    return () => window.clearInterval(timer)
  }, [authorized, hasActiveSlides, isVisible, refresh])

  const used = useMemo(
    () => slides.reduce((total, slide) => total + slide.sourceBytes, 0),
    [slides],
  )

  async function upload() {
    if (!file) return
    if (!/\.ome\.tiff?$/i.test(file.name)) {
      setNotice('Choose a file ending in .ome.tif or .ome.tiff.')
      return
    }
    setNotice('Preparing resumable upload…')
    try {
      const reservation = await reserveUpload(
        file,
        displayName.trim() || file.name.replace(/\.ome\.tiff?$/i, ''),
      )
      setNotice('Upload prepared — it will resume automatically if interrupted.')
      setProgress(0)
      await startTusUpload(file, reservation.uploadUrl, reservation.uploadToken, {
        progress: setProgress,
        success: () => {
          setNotice('Upload complete. Processing is queued.')
          setProgress(100)
          void refresh()
        },
        error: (message) => setNotice(`Upload paused: ${message}`),
      })
      setSlides((current) => [reservation.slide, ...current])
    } catch (error) {
      setNotice(uploadStartErrorMessage(error))
    }
  }

  async function runSlideAction(slide: AdminSlide, actionName: string) {
    if (actionName === 'delete') await deleteSlide(slide.id)
    else await mutateSlide(slide.id, actionName)
    await refresh()
  }

  async function confirmPublish() {
    if (!slidePendingPublication) return
    await runSlideAction(slidePendingPublication, 'publish')
  }

  async function confirmDelete() {
    if (!slidePendingDeletion) return
    await runSlideAction(slidePendingDeletion, 'delete')
  }

  function endSession(message = '') {
    authEpoch.current += 1
    setSecurityOpen(false)
    setSlidePendingPublication(null)
    setSlidePendingDeletion(null)
    setAuthNotice(message)
    setSlides([])
    setAuthorized(false)
  }

  async function signOut() {
    if (signingOut) return
    setLogoutError('')
    setSigningOut(true)
    try {
      await logout()
      endSession()
    } catch {
      setLogoutError('Sign-out failed. Try again.')
    } finally {
      setSigningOut(false)
    }
  }

  if (signingOut) return <div className="center-state" role="status">Signing out…</div>
  if (authorized === false) {
    return (
      <AuthPanel
        notice={authNotice}
        onSuccess={() => {
          setAuthNotice('')
          void refresh()
        }}
      />
    )
  }
  if (authorized === null) return <div className="center-state">Loading secure workspace…</div>

  return (
    <div className="admin-shell">
      <header className="topbar">
        <Brand />
        <div className="topbar-actions">
          <span className="secure-dot"><Check size={13} /> Secure admin</span>
          <button
            type="button"
            className="icon-button"
            aria-label="Account security"
            onClick={() => setSecurityOpen(true)}
          >
            <KeyRound size={18} />
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="Sign out"
            onClick={() => void signOut()}
          >
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <main className="admin-main">
        {logoutError ? <p className="form-error" role="alert">{logoutError}</p> : null}
        <section className="page-heading">
          <div>
            <p className="eyebrow">Slide operations</p>
            <h1>Whole-slide workspace</h1>
            <p>Upload private OME-TIFF originals, review the derivative, then publish an unlisted link.</p>
          </div>
          <div className="storage-summary">
            <span>{formatBytes(used)} stored</span>
            <strong>{Math.max(0, 120 - used / 1024 ** 3).toFixed(1)} GB available</strong>
            <div><i style={{ width: `${Math.min(100, used / (120 * 1024 ** 3) * 100)}%` }} /></div>
          </div>
        </section>

        <div className="admin-grid">
          <section className="panel upload-panel">
            <div className="panel-heading">
              <span className="panel-icon"><CloudUpload size={20} /></span>
              <div>
                <h2>Add a slide</h2>
                <p>Private until you publish it</p>
              </div>
            </div>
            <button type="button" className="drop-zone" onClick={() => fileInput.current?.click()}>
              <CloudUpload size={28} />
              <strong>{file ? file.name : 'Choose OME-TIFF'}</strong>
              <span>Up to 5 GiB · resumable</span>
            </button>
            <input
              ref={fileInput}
              className="visually-hidden"
              id="ome-file"
              aria-label="Choose OME-TIFF"
              type="file"
              accept=".ome.tif,.ome.tiff,image/tiff"
              onChange={(event) => {
                const next = event.target.files?.[0] ?? null
                setFile(next)
                if (next) setDisplayName(next.name.replace(/\.ome\.tiff?$/i, ''))
              }}
            />
            <label className="field-label">
              Public title
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="e.g. HER2 control"
              />
            </label>
            <p className="privacy-note">
              This title is shown to public viewers after publication. Do not include patient names, record numbers, dates of birth, or contact details.
            </p>
            {progress !== null ? (
              <div className="upload-progress"><span style={{ width: `${progress}%` }} /></div>
            ) : null}
            {notice ? <p className="upload-notice">{notice}</p> : null}
            <button className="button primary wide" disabled={!file} onClick={() => void upload()}>
              Upload slide
            </button>
            <p className="privacy-note">
              The original remains private. Public links serve sanitized JPEG tiles only.
            </p>
          </section>

          <section className="panel slide-panel">
            <div className="panel-heading list-heading">
              <div>
                <h2>Your slides</h2>
                <p>{slides.length} {slides.length === 1 ? 'slide' : 'slides'}</p>
              </div>
              <button className="icon-button" aria-label="Refresh slides" onClick={() => void refresh()}>
                <RefreshCw size={17} />
              </button>
            </div>
            <div className="slide-list">
              {slides.length === 0 ? (
                <div className="empty-state">No slides yet. Your first upload will appear here.</div>
              ) : slides.map((slide) => (
                <article className="slide-row" key={slide.id}>
                  <div className="slide-thumb">
                    <span>{slide.metadata ? `${Math.round(slide.metadata.width / 1000)}k` : 'WSI'}</span>
                  </div>
                  <div className="slide-info">
                    <div className="slide-title-line">
                      <h3>{slide.displayName}</h3>
                      <span className={`status status-${slide.state}`}>
                        {slide.state === 'failed' ? <CircleAlert size={13} /> : null}
                        {LABELS[slide.state]}
                      </span>
                    </div>
                    <p>{slide.filename} · {formatBytes(slide.sourceBytes)}</p>
                    {slide.errorMessage ? <p className="row-error">{slide.errorMessage}</p> : null}
                    <div className="row-actions">
                      {slide.state === 'ready_private' ? (
                        <>
                          <a className="text-action" href={`/admin/preview/${slide.id}`}>
                            <Eye size={15} /> Preview
                          </a>
                          <button onClick={() => setSlidePendingPublication(slide)}>Publish</button>
                        </>
                      ) : null}
                      {slide.state === 'published' ? (
                        <>
                          <a className="text-action" href={`/s/${slide.publicId}`}>
                            <Eye size={15} /> View
                          </a>
                          <button
                            onClick={() => void navigator.clipboard.writeText(`${location.origin}/s/${slide.publicId}`)}
                          >
                            <Copy size={14} /> Copy link
                          </button>
                          <button onClick={() => void runSlideAction(slide, 'unpublish')}>Unpublish</button>
                        </>
                      ) : null}
                      {slide.state === 'failed' ? (
                        <button onClick={() => void runSlideAction(slide, 'retry')}>
                          <RefreshCw size={14} /> Retry
                        </button>
                      ) : null}
                      <button
                        className="danger-action"
                        aria-label={`Delete ${slide.displayName}`}
                        onClick={() => setSlidePendingDeletion(slide)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      </main>

      <PublishSlideDialog
        slideName={slidePendingPublication?.displayName ?? null}
        onClose={() => setSlidePendingPublication(null)}
        onConfirm={confirmPublish}
      />
      <DeleteSlideDialog
        slideName={slidePendingDeletion?.displayName ?? null}
        onClose={() => setSlidePendingDeletion(null)}
        onConfirm={confirmDelete}
      />
      <AccountSecurityDialog
        open={securityOpen}
        onClose={() => setSecurityOpen(false)}
        onChanged={() => endSession('Password changed. Sign in again.')}
        onAuthenticationRequired={() => endSession('Session expired. Sign in again.')}
      />
    </div>
  )
}
