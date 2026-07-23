import { useEffect, useRef, useState } from 'react'
import type { FormEvent, SyntheticEvent } from 'react'

interface PublishSlideDialogProps {
  slideName: string | null
  onClose: () => void
  onConfirm: () => Promise<void>
}

export function PublishSlideDialog({ slideName, onClose, onConfirm }: PublishSlideDialogProps) {
  const dialog = useRef<HTMLDialogElement>(null)
  const cancelButton = useRef<HTMLButtonElement>(null)
  const busyRef = useRef(false)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const open = slideName !== null

  useEffect(() => {
    const element = dialog.current
    if (!element) return
    if (open) {
      setConfirmed(false)
      setError('')
      if (!element.open) element.showModal()
      cancelButton.current?.focus()
    } else if (element.open) {
      element.close()
    }
    return () => {
      if (element.open) element.close()
    }
  }, [open])

  function close() {
    if (busyRef.current) return
    setConfirmed(false)
    setError('')
    dialog.current?.close()
    onClose()
  }

  function cancel(event: SyntheticEvent<HTMLDialogElement>) {
    event.preventDefault()
    close()
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busyRef.current || !slideName || !confirmed) return
    busyRef.current = true
    setBusy(true)
    setError('')
    try {
      await onConfirm()
      dialog.current?.close()
      onClose()
    } catch {
      setError('The slide could not be published. Try again.')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <dialog
      ref={dialog}
      className="security-dialog publish-dialog"
      aria-labelledby="publish-slide-title"
      aria-describedby="publish-slide-description"
      onCancel={cancel}
    >
      <form className="security-form" onSubmit={submit}>
        <div>
          <p className="eyebrow">Privacy check</p>
          <h2 id="publish-slide-title">Publish slide?</h2>
        </div>
        <div id="publish-slide-description" className="publish-dialog-copy">
          <p>
            Publishing <strong>{slideName}</strong> creates an unlisted public link. Anyone with the link can view and share it.
          </p>
          <p>
            Confirm that the public title and visible slide image contain no patient names, medical record numbers, dates of birth, contact details, or other identifying information.
          </p>
        </div>
        <label className="privacy-confirmation">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
            disabled={busy}
          />
          <span>I confirm this slide is de-identified.</span>
        </label>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="auth-actions">
          <button ref={cancelButton} className="button" type="button" onClick={close} disabled={busy}>
            Cancel
          </button>
          <button className="button primary" type="submit" disabled={busy || !confirmed}>
            {busy ? 'Publishing…' : 'Publish slide'}
          </button>
        </div>
      </form>
    </dialog>
  )
}
