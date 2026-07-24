import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SlideDetailsPanel } from '../components/library/SlideDetailsPanel'
import type { LibrarySlide } from '../types'

const slide: LibrarySlide = {
  id: 'slide-1',
  publicId: 'public-1',
  displayName: 'Test slide',
  description: '',
  folderId: null,
  caseId: '',
  organSite: '',
  stain: '',
  diagnosis: '',
  course: '',
  tags: [],
  teachingNote: '',
  sourceBytes: 1,
  derivativeBytes: 1,
  state: 'ready_private',
  errorCode: null,
  createdAt: '2026-07-24T00:00:00Z',
  updatedAt: '2026-07-24T00:00:00Z',
  trashedAt: null,
  thumbnailUrl: null,
}

describe('slide publication details', () => {
  it('uses a closed lock for private slides and an open lock for published slides', () => {
    const { rerender } = render(
      <SlideDetailsPanel slide={slide} onClose={vi.fn()} onEdit={vi.fn()} />,
    )

    expect(screen.getByText('Private').closest('dd')?.querySelector('.lucide-lock')).not.toBeNull()
    expect(screen.getByText('Private').closest('dd')?.querySelector('.lucide-lock-open')).toBeNull()

    rerender(
      <SlideDetailsPanel
        slide={{ ...slide, state: 'published' }}
        onClose={vi.fn()}
        onEdit={vi.fn()}
      />,
    )

    expect(screen.getByText('Published').closest('dd')?.querySelector('.lucide-lock-open')).not.toBeNull()
    expect(screen.getByText('Published').closest('dd')?.querySelector('.lucide-lock')).toBeNull()
  })
})
