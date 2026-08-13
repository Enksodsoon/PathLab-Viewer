import { render } from '@testing-library/react'
import type OpenSeadragon from 'openseadragon'
import { describe, expect, it, vi } from 'vitest'

import { ClassroomPinOverlays } from '../classroom/ClassroomPinOverlays'

describe('ClassroomPinOverlays', () => {
  it('places a labelled student pin on the matching slide', () => {
    const addOverlay = vi.fn()
    const viewer = {
      addHandler: vi.fn(),
      addOverlay,
      removeHandler: vi.fn(),
      removeOverlay: vi.fn(),
      world: {
        getItemAt: () => ({
          source: { dimensions: { x: 4000, y: 3000 } },
          imageToViewportCoordinates: (x: number, y: number) => ({ x, y }),
        }),
      },
    } as unknown as OpenSeadragon.Viewer

    render(<ClassroomPinOverlays
      viewer={viewer}
      slideId="slide-1"
      pins={[{
        participantId: 'participant-1',
        alias: 'CORAL-48',
        slideId: 'slide-1',
        x: 0.25,
        y: 0.5,
      }]}
    />)

    expect(addOverlay).toHaveBeenCalledOnce()
    const element = addOverlay.mock.calls[0][0].element as HTMLElement
    expect(element).toHaveAttribute('aria-label', 'CORAL-48 pinned this point')
    expect(element).toHaveTextContent('CORAL-48')
  })
})
