import '@testing-library/jest-dom/vitest'

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = ResizeObserverStub as typeof ResizeObserver
Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
  value: () => null,
})

const dialogState = new WeakMap<
  HTMLDialogElement,
  { returnFocus: HTMLElement | null; keyHandler: (event: KeyboardEvent) => void }
>()

if (typeof HTMLDialogElement !== 'undefined' && !HTMLDialogElement.prototype.showModal) {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true,
    value(this: HTMLDialogElement) {
      if (this.open) throw new DOMException('The dialog is already open.', 'InvalidStateError')
      const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
      const keyHandler = (event: KeyboardEvent) => {
        if (event.key !== 'Escape' || !this.open) return
        const cancelled = !this.dispatchEvent(new Event('cancel', { cancelable: true }))
        if (!cancelled) this.close()
      }
      dialogState.set(this, { returnFocus, keyHandler })
      this.setAttribute('open', '')
      document.addEventListener('keydown', keyHandler)
    },
  })

  Object.defineProperty(HTMLDialogElement.prototype, 'close', {
    configurable: true,
    value(this: HTMLDialogElement) {
      if (!this.open) return
      const state = dialogState.get(this)
      this.removeAttribute('open')
      if (state) {
        document.removeEventListener('keydown', state.keyHandler)
        state.returnFocus?.focus()
        dialogState.delete(this)
      }
      this.dispatchEvent(new Event('close'))
    },
  })
}
