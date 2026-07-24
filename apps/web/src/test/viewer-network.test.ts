import { describe, expect, it } from 'vitest'

import {
  initialViewerNetworkState,
  nextViewerNetworkState,
  type ViewerNetworkWindow,
} from '../viewerNetwork'

const healthy: ViewerNetworkWindow = {
  online: true,
  sampleCount: 12,
  failureRate: 0,
  p75Ms: 250,
}

describe('adaptive viewer request policy', () => {
  it('uses bounded initial limits for the connection and viewport', () => {
    expect(initialViewerNetworkState('auto', false, { effectiveType: '4g', saveData: false }).jobLimit).toBe(12)
    expect(initialViewerNetworkState('auto', true, { effectiveType: '4g', saveData: false }).jobLimit).toBe(8)
    expect(initialViewerNetworkState('auto', false, { effectiveType: '2g', saveData: false }).jobLimit).toBe(2)
    expect(initialViewerNetworkState('auto', false, { effectiveType: '4g', saveData: true }).jobLimit).toBe(2)
  })

  it('drops concurrency immediately for slow or failing tile windows', () => {
    const start = initialViewerNetworkState('auto', false)
    expect(nextViewerNetworkState(start, { ...healthy, p75Ms: 1200, failureRate: 0.02 }, false).jobLimit).toBe(4)
    expect(nextViewerNetworkState(start, { ...healthy, p75Ms: 2200 }, false).jobLimit).toBe(2)
    expect(nextViewerNetworkState(start, { ...healthy, online: false }, false).jobLimit).toBe(2)
  })

  it('requires two healthy windows before increasing concurrency', () => {
    const constrained = { jobLimit: 2, healthyWindows: 0 }
    const first = nextViewerNetworkState(constrained, healthy, false)
    expect(first).toEqual({ jobLimit: 2, healthyWindows: 1 })
    expect(nextViewerNetworkState(first, healthy, false)).toEqual({ jobLimit: 12, healthyWindows: 0 })
  })

  it('keeps explicit data-saver and full-detail modes deterministic', () => {
    const start = initialViewerNetworkState('auto', false)
    expect(nextViewerNetworkState(start, healthy, false, 'data-saver').jobLimit).toBe(2)
    expect(nextViewerNetworkState(start, { ...healthy, p75Ms: 5000 }, false, 'full').jobLimit).toBe(12)
    expect(nextViewerNetworkState(start, healthy, true, 'full').jobLimit).toBe(8)
  })
})
