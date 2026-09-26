import type OpenSeadragon from 'openseadragon'
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ClassroomQuestionComposer } from '../classroom/ClassroomQuestionComposer'
it('anchors to image coordinates, submits with Command Enter, and removes its overlay', () => {
  const submit = vi.fn()
  const addOverlay = vi.fn(({ element }) => document.body.append(element))
  const removeOverlay = vi.fn((element: HTMLElement) => element.remove())
  const viewer = { addOverlay, removeOverlay, addHandler: vi.fn(), removeHandler: vi.fn(), world: { getItemAt: () => ({ source: { dimensions: { x: 4000, y: 2000 } }, imageToViewportCoordinates: (x: number, y: number) => ({ x, y }) }) } } as unknown as OpenSeadragon.Viewer
  const { unmount } = render(<ClassroomQuestionComposer viewer={viewer} pin={{ x: .25, y: .5 }} question="Why?" busy={false} onQuestion={vi.fn()} onSubmit={submit} onCancel={vi.fn()} />)
  expect(addOverlay.mock.calls[0][0].location).toEqual({ x: 1000, y: 1000 })
  fireEvent.keyDown(screen.getByLabelText('Question at this point'), { key: 'Enter', metaKey: true })
  expect(submit).toHaveBeenCalledOnce()
  unmount()
  expect(removeOverlay).toHaveBeenCalledOnce()
})
