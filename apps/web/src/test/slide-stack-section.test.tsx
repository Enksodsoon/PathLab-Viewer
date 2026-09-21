import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SlideStackSection } from '../components/library/SlideStackSection'
import type { LibrarySlide, SlideStackSummary } from '../types'

const createComparisonSet = vi.fn()
const getSlideStacks = vi.fn()

vi.mock('../api', () => ({
  createComparisonSet: (...args: unknown[]) => createComparisonSet(...args),
  getSlideStacks: (...args: unknown[]) => getSlideStacks(...args),
}))

const slide: LibrarySlide = {
  id: 'slide-he', publicId: 'public-he', displayName: 'H&E', description: '', folderId: null,
  caseId: 'case-1', organSite: 'breast', stain: 'H&E', diagnosis: '', course: '', tags: [],
  teachingNote: '', sourceBytes: 1, derivativeBytes: 1, state: 'ready_private', errorCode: null,
  createdAt: '2026-09-21T00:00:00Z', updatedAt: '2026-09-21T00:00:00Z', trashedAt: null,
  thumbnailUrl: null,
}

const summary: SlideStackSummary = {
  id: 'stack-1', name: 'Breast serial stains', status: 'partial', version: 1,
  referenceSlideId: 'slide-he', role: 'reference', memberCount: 2, stains: ['H&E', 'HER2'],
}

describe('slide stack details summary', () => {
  beforeEach(() => {
    createComparisonSet.mockReset().mockResolvedValue({ id: 'stack-1' })
    getSlideStacks.mockReset().mockResolvedValue([summary])
  })

  it('summarizes memberships and directs management to the visual shelf', async () => {
    render(<SlideStackSection slide={slide} enabled />)
    expect(await screen.findByRole('link', { name: 'Open' })).toHaveAttribute('href', '/admin/comparisons/stack-1')
    expect(screen.getByText('2 slides · This slide is the reference')).toBeInTheDocument()
    expect(screen.getByText('H&E · HER2 · partial')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Manage in Slide stacks/i })).toHaveAttribute('href', '/admin#slide-stacks')
    expect(screen.queryByRole('button', { name: /Organize/i })).not.toBeInTheDocument()
  })

  it('starts a one-slide stack when there are no memberships', async () => {
    getSlideStacks.mockResolvedValue([])
    render(<SlideStackSection slide={slide} enabled />)
    fireEvent.click(await screen.findByRole('button', { name: /Start a stack with this slide/i }))
    await waitFor(() => expect(createComparisonSet).toHaveBeenCalledWith('case-1 slide stack', ['slide-he'], 'slide-he'))
  })

  it('is hidden with the alignment capability disabled', () => {
    const { container } = render(<SlideStackSection slide={slide} enabled={false} />)
    expect(container).toBeEmptyDOMElement()
    expect(getSlideStacks).not.toHaveBeenCalled()
  })
})