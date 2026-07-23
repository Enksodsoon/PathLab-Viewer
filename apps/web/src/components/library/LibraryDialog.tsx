import { X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'

interface LibraryDialogProps {
  open: boolean
  title: string
  description?: string
  children: ReactNode
  onClose: () => void
}

export function LibraryDialog({
  open,
  title,
  description,
  children,
  onClose,
}: LibraryDialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      className="library-dialog"
      aria-labelledby="library-dialog-title"
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onClose={onClose}
    >
      <div className="library-dialog-heading">
        <div>
          <h2 id="library-dialog-title">{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        <button type="button" aria-label={`Close ${title}`} onClick={onClose}><X /></button>
      </div>
      {children}
    </dialog>
  )
}
