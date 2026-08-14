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

export interface ViewerNetworkProfile {
  initialJobLimit?: number
  maximumJobLimit?: number
}

export const CLASSROOM_VIEWER_NETWORK_PROFILE: ViewerNetworkProfile = Object.freeze({
  initialJobLimit: 2,
  maximumJobLimit: 4,
})

function maximumLimit(narrowViewport: boolean, profile?: ViewerNetworkProfile) {
  return Math.max(2, Math.min(narrowViewport ? 8 : 12, profile?.maximumJobLimit ?? 12))
}

export function initialViewerNetworkState(
  mode: ViewerLoadingMode,
  narrowViewport: boolean,
  connection?: ViewerConnectionHint,
  profile?: ViewerNetworkProfile,
): ViewerNetworkState {
  const maximum = maximumLimit(narrowViewport, profile)
  if (profile?.initialJobLimit !== undefined) {
    return { jobLimit: Math.max(2, Math.min(maximum, profile.initialJobLimit)), healthyWindows: 0 }
  }
  if (mode === 'data-saver' || connection?.saveData || connection?.effectiveType === '2g' || connection?.effectiveType === 'slow-2g') {
    return { jobLimit: 2, healthyWindows: 0 }
  }
  if (mode === 'auto' && connection?.effectiveType === '3g') {
    return { jobLimit: Math.min(4, maximum), healthyWindows: 0 }
  }
  return { jobLimit: maximum, healthyWindows: 0 }
}

function targetLimit(
  window: ViewerNetworkWindow,
  narrowViewport: boolean,
  profile?: ViewerNetworkProfile,
) {
  const maximum = maximumLimit(narrowViewport, profile)
  if (!window.online || window.failureRate > 0.05 || window.p75Ms > 2000) return 2
  if (window.failureRate > 0.01 || window.p75Ms > 1000) return Math.min(4, maximum)
  if (window.p75Ms > 400) return Math.min(8, maximum)
  return maximum
}

export function nextViewerNetworkState(
  current: ViewerNetworkState,
  window: ViewerNetworkWindow,
  narrowViewport: boolean,
  mode: ViewerLoadingMode = 'auto',
  profile?: ViewerNetworkProfile,
): ViewerNetworkState {
  if (mode !== 'auto') {
    const explicit = initialViewerNetworkState(mode, narrowViewport, undefined, profile)
    return profile?.initialJobLimit === undefined
      ? explicit
      : { ...explicit, jobLimit: maximumLimit(narrowViewport, profile) }
  }
  if (!window.online) return { jobLimit: 2, healthyWindows: 0 }
  if (window.sampleCount < 12) return current

  const target = targetLimit(window, narrowViewport, profile)
  if (target < current.jobLimit) return { jobLimit: target, healthyWindows: 0 }
  if (target === current.jobLimit) return { jobLimit: current.jobLimit, healthyWindows: 0 }

  const healthyWindows = current.healthyWindows + 1
  return healthyWindows >= 2
    ? { jobLimit: target, healthyWindows: 0 }
    : { jobLimit: current.jobLimit, healthyWindows }
}
