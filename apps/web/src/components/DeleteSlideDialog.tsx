import { useEffect, useRef, useState } from 'react'
import type { FormEvent, SyntheticEvent } from 'react'

interface DeleteSlideDialogProps {
  slideName: string | null
  onClose: () => void
  onConfirm: () => Promise<void>
}

export function DeleteSlideDialog({ slideName, onClose, onConfirm }: DeleteSlideDialogProps) {
  const dialog = useRef<HTMLDialogElement>(null)
  const cancelButton = useRef<HTMLButtonElement>(null)
  const busyRef = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const open = slideName !== null

  useEffect(() => {
    const element = dialog.current
    if (!element) return
    if (open) {
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
    if (busyRef.current || !slideName) return
    busyRef.current = true
    setBusy(true)
    setError('')
    try {
      await onConfirm()
      dialog.current?.close()
      onClose()
    } catch {
      setError('The slide could not be deleted. Try again.')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <dialog
      ref={dialog}
      className="security-dialog delete-dialog"
      aria-labelledby="delete-slide-title"
      aria-describedby="delete-slide-description"
      onCancel={cancel}
    >
      <form className="security-form" onSubmit={submit}>
        <div>
          <p className="eyebrow">Confirm deletion</p>
          <h2 id="delete-slide-title">Delete slide?</h2>
        </div>
        <p id="delete-slide-description" className="delete-dialog-copy">
          This permanently removes <strong>{slideName}</strong> and its stored files. This action cannot be undone.
        </p>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="auth-actions">
          <button ref={cancelButton} className="button" type="button" onClick={close} disabled={busy}>
            Cancel
          </button>
          <button className="button danger" type="submit" disabled={busy}>
            {busy ? 'Deleting…' : 'Delete slide'}
          </button>
        </div>
      </form>
    </dialog>
  )
}
