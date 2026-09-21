import { cleanup, fireEvent, render, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SlideStackShelf } from '../components/library/SlideStackShelf'
import type { ComparisonSet, LibrarySlide } from '../types'

const listComparisonSets = vi.fn()
const getComparisonSet = vi.fn()
const getStackSuggestions = vi.fn()
const updateStackMembers = vi.fn()
const createComparisonSet = vi.fn()

vi.mock('../api', () => ({
  createComparisonSet: (...args: unknown[]) => createComparisonSet(...args),
  getComparisonSet: (...args: unknown[]) => getComparisonSet(...args),
  getLibrarySlide: vi.fn(),
  getStackSuggestions: (...args: unknown[]) => getStackSuggestions(...args),
  listComparisonSets: (...args: unknown[]) => listComparisonSets(...args),
  reserveStackUpload: vi.fn(),
  updateStackMembers: (...args: unknown[]) => updateStackMembers(...args),
}))

const slide: LibrarySlide = {
  id: 'slide-he', publicId: 'public-he', displayName: 'H&E block A', description: '', folderId: 'folder-1',
  caseId: 'case-1', organSite: 'breast', stain: 'H&E', diagnosis: '', course: '', tags: [],
  teachingNote: '', sourceBytes: 1, derivativeBytes: 1, state: 'ready_private', errorCode: null,
  createdAt: '2026-09-21T00:00:00Z', updatedAt: '2026-09-21T00:00:00Z', trashedAt: null,
  thumbnailUrl: '/he.jpg',
}

const stack: ComparisonSet = {
  id: 'stack-1', name: 'Breast block A', status: 'partial', version: 3,
  referenceSlideId: 'slide-he',
  members: [
    {
      slideId: 'slide-he', displayName: 'H&E block A', stain: 'H&E', tileSource: '/he.dzi',
      thumbnailUrl: '/he.jpg', metadata: null, registration: null, state: 'ready_private', anchorSlideId: null,
    },
    {
      slideId: 'slide-her2', displayName: 'HER2 block A', stain: 'HER2', tileSource: '/her2.dzi',
      thumbnailUrl: '/her2.jpg', metadata: null, state: 'ready_private', anchorSlideId: 'slide-he',
      registration: { status: 'ready', provenance: 'automatic', anchorSlideId: 'slide-he', confidence: .9 },
    },
  ],
}

describe('expandable slide stack shelf', () => {
  afterEach(cleanup)

  beforeEach(() => {
    listComparisonSets.mockReset().mockResolvedValue([stack])
    getComparisonSet.mockReset().mockResolvedValue(stack)
    getStackSuggestions.mockReset().mockResolvedValue([])
    updateStackMembers.mockReset().mockResolvedValue(stack)
    createComparisonSet.mockReset().mockResolvedValue(stack)
  })

  it('opens a visual stack and keeps advanced controls collapsed', async () => {
    const view = render(<SlideStackShelf enabled slides={[slide]} />)

    const stackButton = await view.findByRole('button', { name: /Breast block A/i })
    fireEvent.click(stackButton)

    expect(await view.findByRole('link', { name: 'View side by side' })).toHaveAttribute(
      'href', '/admin/comparisons/stack-1',
    )
    expect(view.getByText('Reference')).toBeInTheDocument()
    expect(view.getByText('Aligned')).toBeInTheDocument()
    expect(view.getByRole('button', { name: /Drop stained slides here/i })).toBeInTheDocument()
    expect(view.getByText(/Most stacks need no changes here/)).not.toBeVisible()
  })

  it('queues dropped OME-TIFFs with useful stain guesses', async () => {
    const view = render(<SlideStackShelf enabled slides={[slide]} />)
    fireEvent.click(await view.findByRole('button', { name: /Breast block A/i }))
    await view.findByRole('link', { name: 'View side by side' })

    const input = view.container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['x'], 'case-a_HER2.ome.tiff', { type: 'image/tiff' })] } })

    expect(await view.findByDisplayValue('case-a HER2')).toBeInTheDocument()
    expect(view.getByDisplayValue('HER2')).toBeInTheDocument()
    expect(view.getByRole('button', { name: 'Upload 1 slide' })).toBeInTheDocument()
  })

  it('recognizes common pulmonary IHC markers from filenames', async () => {
    const view = render(<SlideStackShelf enabled slides={[slide]} />)
    fireEvent.click(await view.findByRole('button', { name: /Breast block A/i }))
    await view.findByRole('link', { name: 'View side by side' })

    const input = view.container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [
      new File(['x'], 'case-a_P40.ome.tiff', { type: 'image/tiff' }),
      new File(['x'], 'case-a_TTF1.ome.tiff', { type: 'image/tiff' }),
    ] } })

    expect(await view.findByDisplayValue('P40')).toBeInTheDocument()
    expect(view.getByDisplayValue('TTF1')).toBeInTheDocument()
  })

  it('reorders stack cards with drag and drop', async () => {
    const view = render(<SlideStackShelf enabled slides={[slide]} />)
    fireEvent.click(await view.findByRole('button', { name: /Breast block A/i }))
    await view.findByRole('link', { name: 'View side by side' })
    const cards = view.container.querySelectorAll('.stack-member-card')
    fireEvent.dragStart(cards[1])
    fireEvent.dragOver(cards[0])
    fireEvent.drop(cards[0])
    await waitFor(() => expect(updateStackMembers).toHaveBeenCalledWith('stack-1', {
      version: 3,
      add: [],
      order: ['slide-her2', 'slide-he'],
    }))
  })

  it('adds existing slides through a plain library picker', async () => {
    getStackSuggestions.mockResolvedValue([{
      slideId: 'slide-pas', displayName: 'PAS block A', stain: 'PAS', caseId: 'case-1',
      organSite: 'breast', folderId: 'folder-1', thumbnailUrl: '/pas.jpg', reasons: ['Same case'],
    }])
    const view = render(<SlideStackShelf enabled slides={[slide]} />)
    fireEvent.click(await view.findByRole('button', { name: /Breast block A/i }))
    fireEvent.click(await view.findByRole('button', { name: /Add from library/i }))

    await waitFor(() => expect(getStackSuggestions).toHaveBeenCalledWith('slide-he', ''))
    const candidateLabel = (await view.findByText('PAS block A')).closest('label')
    const candidate = within(candidateLabel as HTMLElement).getByRole('checkbox')
    fireEvent.click(candidate)
    fireEvent.click(view.getByRole('button', { name: 'Add 1 slide' }))
    await waitFor(() => expect(updateStackMembers).toHaveBeenCalledWith('stack-1', {
      version: 3,
      add: [{ slideId: 'slide-pas', anchorSlideId: 'slide-he' }],
    }))
  })

  it('creates a stack from a ready slide without exposing alignment settings', async () => {
    listComparisonSets.mockResolvedValue([])
    const view = render(<SlideStackShelf enabled slides={[slide]} />)
    fireEvent.click(await view.findByRole('button', { name: 'New stack' }))
    fireEvent.change(view.getByLabelText('Stack name'), { target: { value: 'Breast serials' } })
    fireEvent.change(view.getByLabelText('First slide'), { target: { value: 'slide-he' } })
    const panel = view.getByText('Choose the first slide').parentElement?.parentElement
    fireEvent.click(within(panel as HTMLElement).getByRole('button', { name: 'Create stack' }))

    await waitFor(() => expect(createComparisonSet).toHaveBeenCalledWith(
      'Breast serials', ['slide-he'], 'slide-he',
    ))
  })

  it('clears files queued in another stack after creating a new stack', async () => {
    const created = { ...stack, id: 'stack-2', name: 'Second stack' }
    listComparisonSets.mockResolvedValueOnce([stack]).mockResolvedValue([created])
    createComparisonSet.mockResolvedValue(created)
    getComparisonSet.mockResolvedValueOnce(stack).mockResolvedValue(created)
    const view = render(<SlideStackShelf enabled slides={[slide]} />)
    fireEvent.click(await view.findByRole('button', { name: /Breast block A/i }))
    await view.findByRole('link', { name: 'View side by side' })
    const input = view.container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['x'], 'wrong_P40.ome.tiff', { type: 'image/tiff' })] } })
    expect(await view.findByDisplayValue('wrong P40')).toBeInTheDocument()

    fireEvent.click(view.getByRole('button', { name: 'New stack' }))
    fireEvent.change(view.getByLabelText('Stack name'), { target: { value: 'Second stack' } })
    fireEvent.change(view.getByLabelText('First slide'), { target: { value: 'slide-he' } })
    const panel = view.getByText('Choose the first slide').parentElement?.parentElement
    fireEvent.click(within(panel as HTMLElement).getByRole('button', { name: 'Create stack' }))

    await waitFor(() => expect(view.queryByDisplayValue('wrong P40')).not.toBeInTheDocument())
  })
})
