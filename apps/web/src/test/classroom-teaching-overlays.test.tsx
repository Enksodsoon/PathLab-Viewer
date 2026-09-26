import { act, cleanup, render } from '@testing-library/react'
import type OpenSeadragon from 'openseadragon'
import { afterEach, expect, it, vi } from 'vitest'
import { ClassroomTeachingOverlays } from '../classroom/ClassroomTeachingOverlays'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('clears rendered canvas when the last annotation is removed or the new slide has no image', () => {
  const context = { setTransform: vi.fn(), clearRect: vi.fn(), save: vi.fn(), restore: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn() }
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 320, height: 180 } as DOMRect)
  const frames: FrameRequestCallback[] = []
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => { frames.push(callback); return frames.length })
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined)
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  let imagePresent = true
  const viewer = { container: document.createElement('div'), addHandler: vi.fn(), removeHandler: vi.fn(),
    world: { getItemAt: () => imagePresent ? { source: { dimensions: { x: 100, y: 100 } }, imageToViewportCoordinates: (x: number, y: number) => ({ x, y }) } : undefined },
    viewport: { viewportToViewerElementCoordinates: (point: unknown) => point },
  } as unknown as OpenSeadragon.Viewer
  const annotation = { id: 'mark', slideId: 'one', tool: 'line' as const, color: '#ef765f' as const, width: 2 as const, points: [{ x: .1, y: .1 }, { x: .4, y: .4 }] }
  function flush() { act(() => { for (const callback of frames.splice(0)) callback(0) }) }
  const { rerender } = render(<ClassroomTeachingOverlays viewer={viewer} slideId="one" annotations={[annotation]} pointer={null} />)
  flush()
  expect(context.stroke).toHaveBeenCalledOnce()
  context.clearRect.mockClear()
  rerender(<ClassroomTeachingOverlays viewer={viewer} slideId="one" annotations={[]} pointer={null} />)
  flush()
  expect(context.clearRect).toHaveBeenCalledWith(0, 0, 320, 180)
  rerender(<ClassroomTeachingOverlays viewer={viewer} slideId="one" annotations={[annotation]} pointer={null} />)
  flush()
  context.clearRect.mockClear()
  imagePresent = false
  rerender(<ClassroomTeachingOverlays viewer={viewer} slideId="two" annotations={[annotation]} pointer={null} />)
  flush()
  expect(context.clearRect).toHaveBeenCalledWith(0, 0, 320, 180)
})
