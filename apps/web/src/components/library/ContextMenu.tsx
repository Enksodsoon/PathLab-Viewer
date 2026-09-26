import {
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'
import { createPortal } from 'react-dom'

interface ContextMenuProps {
  label: string
  buttonClassName?: string
  buttonContent: ReactNode
  children: (close: () => void) => ReactNode
}

export function ContextMenu({
  label,
  buttonClassName,
  buttonContent,
  children,
}: ContextMenuProps) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({ left: 8, top: 8 })
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const close = () => {
    setOpen(false)
    window.requestAnimationFrame(() => triggerRef.current?.focus({ preventScroll: true }))
  }

  useLayoutEffect(() => {
    if (!open) return
    const reposition = () => {
      if (!triggerRef.current || !menuRef.current) return
      const trigger = triggerRef.current.getBoundingClientRect()
      const menu = menuRef.current.getBoundingClientRect()
      const gap = 6
      const left = Math.max(8, Math.min(
        trigger.right - menu.width,
        window.innerWidth - menu.width - 8,
      ))
      const top = trigger.bottom + gap + menu.height <= window.innerHeight
        ? trigger.bottom + gap
        : Math.max(8, trigger.top - menu.height - gap)
      setPosition({ left, top })
    }
    reposition()
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus({ preventScroll: true })
    window.addEventListener('resize', reposition)
    window.addEventListener('scroll', reposition, true)
    return () => {
      window.removeEventListener('resize', reposition)
      window.removeEventListener('scroll', reposition, true)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (!menuRef.current?.contains(target) && !triggerRef.current?.contains(target)) close()
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [open])

  function moveFocus(event: KeyboardEvent<HTMLDivElement>) {
    const items = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])'),
    )
    const current = items.indexOf(document.activeElement as HTMLElement)
    let next = current
    if (event.key === 'ArrowDown') next = (current + 1) % items.length
    else if (event.key === 'ArrowUp') next = (current - 1 + items.length) % items.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = items.length - 1
    else if (event.key === 'Escape') {
      event.preventDefault()
      close()
      return
    } else return
    event.preventDefault()
    items[next]?.focus({ preventScroll: true })
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={buttonClassName}
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (!open && (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ')) {
            event.preventDefault()
            setOpen(true)
          }
        }}
      >
        {buttonContent}
      </button>
      {open ? createPortal(
        <div
          ref={menuRef}
          className="library-menu library-menu-portal"
          role="menu"
          style={{ left: position.left, top: position.top }}
          onKeyDown={moveFocus}
        >
          {children(close)}
        </div>,
        document.body,
      ) : null}
    </>
  )
}
