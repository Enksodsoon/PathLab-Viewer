export type ViewerLoadingMode = 'auto' | 'data-saver' | 'full'

export interface ViewerConnectionHint {
  effectiveType?: string
  saveData?: boolean
}

export interface ViewerNetworkWindow {
  online: boolean
  sampleCount: number
  failureRate: number
  p75Ms: number
}

export interface ViewerNetworkState {
  jobLimit: number
  healthyWindows: number
}

function maximumLimit(narrowViewport: boolean) {
  return narrowViewport ? 8 : 12
}

export function initialViewerNetworkState(
  mode: ViewerLoadingMode,
  narrowViewport: boolean,
  connection?: ViewerConnectionHint,
): ViewerNetworkState {
  if (mode === 'data-saver' || connection?.saveData || connection?.effectiveType === '2g' || connection?.effectiveType === 'slow-2g') {
    return { jobLimit: 2, healthyWindows: 0 }
  }
  if (mode === 'auto' && connection?.effectiveType === '3g') {
    return { jobLimit: 4, healthyWindows: 0 }
  }
  return { jobLimit: maximumLimit(narrowViewport), healthyWindows: 0 }
}

function targetLimit(window: ViewerNetworkWindow, narrowViewport: boolean) {
  if (!window.online || window.failureRate > 0.05 || window.p75Ms > 2000) return 2
  if (window.failureRate > 0.01 || window.p75Ms > 1000) return 4
  if (window.p75Ms > 400) return Math.min(8, maximumLimit(narrowViewport))
  return maximumLimit(narrowViewport)
}

export function nextViewerNetworkState(
  current: ViewerNetworkState,
  window: ViewerNetworkWindow,
  narrowViewport: boolean,
  mode: ViewerLoadingMode = 'auto',
): ViewerNetworkState {
  if (mode !== 'auto') return initialViewerNetworkState(mode, narrowViewport)
  if (!window.online) return { jobLimit: 2, healthyWindows: 0 }
  if (window.sampleCount < 12) return current

  const target = targetLimit(window, narrowViewport)
  if (target < current.jobLimit) return { jobLimit: target, healthyWindows: 0 }
  if (target === current.jobLimit) return { jobLimit: current.jobLimit, healthyWindows: 0 }

  const healthyWindows = current.healthyWindows + 1
  return healthyWindows >= 2
    ? { jobLimit: target, healthyWindows: 0 }
    : { jobLimit: current.jobLimit, healthyWindows }
}
