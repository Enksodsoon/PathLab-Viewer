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
