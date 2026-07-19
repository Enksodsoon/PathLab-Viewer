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
