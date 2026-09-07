import { afterEach, describe, expect, it, vi } from 'vitest'

import { listEligibleAssessmentSlides } from '../assessment/api'

describe('assessment API', () => {
  afterEach(() => vi.restoreAllMocks())

  it('derives a cache-safe thumbnail from the versioned slide delivery route', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      items: [{
        id: 'slide-a',
        publicId: 'public-slide-a',
        displayName: 'Teaching slide A',
        tileSource: '/tiles/public-slide-a/202608290101/slide.dzi',
        thumbnail: '/tiles/public-slide-a/thumbnail.jpg',
      }],
    })))

    const result = await listEligibleAssessmentSlides('Teaching')

    expect(result.items[0]?.thumbnail).toBe(
      '/tiles/public-slide-a/202608290101/thumbnail.jpg?assessment-preview=1',
    )
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v2/admin/assessment/slides?query=Teaching',
      { credentials: 'same-origin', cache: 'no-store' },
    )
  })
})
