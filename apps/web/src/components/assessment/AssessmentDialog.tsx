import { useLayoutEffect, useRef, type ReactNode } from 'react'

export function AssessmentDialog({ label, onClose, children }: {
  label: string
  onClose: () => void
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useLayoutEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialog.showModal()
    dialog.querySelector<HTMLButtonElement>('button')?.focus()
    return () => {
      if (dialog.open) dialog.close()
      if (returnFocus?.isConnected) returnFocus.focus()
    }
  }, [])

  return <dialog
    ref={ref}
    className="assessment-preview-backdrop"
    aria-label={label}
    onKeyDown={(event) => {
      if (event.key !== 'Tab' || event.ctrlKey || event.metaKey || event.altKey) return
      const controls = [...event.currentTarget.querySelectorAll<HTMLElement>(
        'button,input,select,textarea,summary,a[href],[tabindex]',
      )].filter((element) => element.tabIndex >= 0
        && !element.matches(':disabled') && element.checkVisibility({ visibilityProperty: true }))
      const first = controls[0]
      const last = controls.at(-1)
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first?.focus()
      }
    }}
    onCancel={(event) => { event.preventDefault(); onClose() }}
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}
  >{children}</dialog>
}
