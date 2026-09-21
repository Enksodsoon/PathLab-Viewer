import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SlideStackSection } from '../components/library/SlideStackSection'
import type { ComparisonSet, LibrarySlide, SlideStackSummary } from '../types'

const getSlideStacks = vi.fn()
const getComparisonSet = vi.fn()
const getStackSuggestions = vi.fn()
const updateStackMembers = vi.fn()

vi.mock('../api', () => ({
  createComparisonSet: vi.fn(),
  getComparisonSet: (...args: unknown[]) => getComparisonSet(...args),
  getSlideStacks: (...args: unknown[]) => getSlideStacks(...args),
  getStackSuggestions: (...args: unknown[]) => getStackSuggestions(...args),
  reserveStackUpload: vi.fn(),
  updateStackMembers: (...args: unknown[]) => updateStackMembers(...args),
}))

const slide: LibrarySlide = {
  id: 'slide-he', publicId: 'public-he', displayName: 'H&E', description: '', folderId: null,
  caseId: 'case-1', organSite: 'breast', stain: 'H&E', diagnosis: '', course: '', tags: [],
  teachingNote: '', sourceBytes: 1, derivativeBytes: 1, state: 'ready_private', errorCode: null,
  createdAt: '2026-09-21T00:00:00Z', updatedAt: '2026-09-21T00:00:00Z', trashedAt: null,
  thumbnailUrl: null,
}

const summary: SlideStackSummary = {
  id: 'stack-1', name: 'Breast serial stains', status: 'draft', version: 1,
  referenceSlideId: 'slide-he', role: 'reference', memberCount: 2, stains: ['H&E', 'HER2'],
}

const stack: ComparisonSet = {
  id: 'stack-1', name: summary.name, status: 'draft', version: 1,
  referenceSlideId: 'slide-he',
  members: [
    {
      slideId: 'slide-he', displayName: 'H&E', stain: 'H&E',
      tileSource: '/he.dzi', thumbnailUrl: '/he.jpg', metadata: null, registration: null,
      state: 'ready_private', anchorSlideId: null,
    },
    {
      slideId: 'slide-her2', displayName: 'HER2', stain: 'HER2',
      tileSource: null, thumbnailUrl: null, metadata: null, registration: null,
      state: 'converting', availabilityReason: 'converting', anchorSlideId: 'slide-he',
    },
  ],
}

describe('slide stack details workflow', () => {
  beforeEach(() => {
    getSlideStacks.mockReset().mockResolvedValue([summary])
    getComparisonSet.mockReset().mockResolvedValue(stack)
    getStackSuggestions.mockReset().mockResolvedValue([])
    updateStackMembers.mockReset().mockResolvedValue(stack)
  })

  it('shows every membership and exposes upload and linking workflows', async () => {
    render(<SlideStackSection slide={slide} enabled />)

    expect(await screen.findByRole('link', { name: 'Open stack' })).toHaveAttribute(
      'href', '/admin/comparisons/stack-1',
    )
    expect(screen.getByText('Reference')).toBeInTheDocument()
    expect(screen.getByText('converting')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add stained slides' }))
    expect(screen.getByLabelText('Choose OME-TIFF files')).toHaveAttribute(
      'accept', '.ome.tif,.ome.tiff,image/tiff',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Link existing slides' }))
    await waitFor(() => expect(getStackSuggestions).toHaveBeenCalledWith('slide-he', ''))
    expect(screen.getByRole('searchbox', { name: 'Find slides' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Organize' }))
    expect(screen.getByRole('button', { name: 'Move H&E up' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Remove HER2 from stack' }))
    await waitFor(() => expect(updateStackMembers).toHaveBeenCalledWith('stack-1', {
      version: 1,
      add: [],
      remove: ['slide-her2'],
    }))
  })

  it('is hidden with the alignment capability disabled', () => {
    const { container } = render(<SlideStackSection slide={slide} enabled={false} />)
    expect(container).toBeEmptyDOMElement()
    expect(getSlideStacks).not.toHaveBeenCalled()
  })
})
