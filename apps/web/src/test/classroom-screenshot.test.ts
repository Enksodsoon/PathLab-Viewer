import { describe, expect, it } from 'vitest'

import { boundedCaptureDimensions } from '../classroom/screenshot'

describe('classroom screenshot sizing', () => {
  it('keeps small canvases at their natural size', () => {
    expect(boundedCaptureDimensions(900, 600)).toEqual({ width: 900, height: 600 })
  })

  it('bounds high-density canvases without changing aspect ratio', () => {
    expect(boundedCaptureDimensions(3168, 1984)).toEqual({ width: 1600, height: 1002 })
    expect(boundedCaptureDimensions(1080, 2156)).toEqual({ width: 601, height: 1200 })
  })

  it('rejects an empty canvas', () => {
    expect(() => boundedCaptureDimensions(0, 900)).toThrow('Screenshot canvas is empty')
  })
})
