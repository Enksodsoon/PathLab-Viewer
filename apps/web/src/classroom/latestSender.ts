export interface LatestSender<T> {
  push: (value: T) => void
  dispose: () => void
}

export function createLatestSender<T>(
  send: (value: T) => Promise<void>,
  intervalMs = 50,
): LatestSender<T> {
  let pending: T | null = null
  let timer: number | null = null
  let inFlight = false
  let disposed = false
  let lastSentAt = Number.NEGATIVE_INFINITY

  const schedule = () => {
    if (disposed || inFlight || pending === null || timer !== null) return
    const wait = Math.max(0, intervalMs - (performance.now() - lastSentAt))
    timer = window.setTimeout(() => {
      timer = null
      if (disposed || inFlight || pending === null) return
      const value = pending
      pending = null
      inFlight = true
      lastSentAt = performance.now()
      void send(value).finally(() => {
        inFlight = false
        schedule()
      })
    }, wait)
  }

  return {
    push(value) {
      pending = value
      schedule()
    },
    dispose() {
      disposed = true
      pending = null
      if (timer !== null) window.clearTimeout(timer)
      timer = null
    },
  }
}
