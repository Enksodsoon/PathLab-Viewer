import { afterEach, describe, expect, it, vi } from 'vitest'

import { AssessmentHttpError, listEligibleAssessmentSlides, saveAssessmentDraft } from '../assessment/api'
import type { AssessmentDocument } from '../assessment/types'

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

  it.each(['network', 'server'] as const)('reconciles a committed %s failure without sending a second mutation', async (failure) => {
    const document: AssessmentDocument = { title: 'Committed QA', items: [], settings: { mode: 'practice' } }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(async () => {
        if (failure === 'network') throw new TypeError('Response lost')
        return new Response('{}', { status: 503 })
      })
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'qa', revision: 2, status: 'draft', document: { settings: { mode: 'practice' }, items: [], title: 'Committed QA' } })))
    const saved = await saveAssessmentDraft('qa', 1, document)
    expect(saved.revision).toBe(2)
    expect(saved.document.title).toBe('Committed QA')
    expect(fetchMock.mock.calls.map(call => call[1]?.method ?? 'GET')).toEqual(['PATCH', 'GET'])
  })

  it.each([
    { id: 'qa', revision: 2, title: 'Other writer' },
    { id: 'qa', revision: 1, title: 'Committed QA' },
    { id: 'qa', revision: 3, title: 'Committed QA' },
    { id: 'other', revision: 2, title: 'Committed QA' },
  ])('keeps uncertain save failure when server evidence is not the submitted next revision: %j', async ({ id, revision, title }) => {
    const failure = new TypeError('Response lost')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(failure)
      .mockResolvedValueOnce(new Response(JSON.stringify({ id, revision, document: { title, items: [], settings: {} } })))
    await expect(saveAssessmentDraft('qa', 1, { title: 'Committed QA', items: [], settings: {} })).rejects.toBe(failure)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it.each([401, 403, 409, 422, 429])('does not reconcile HTTP%s denial or conflict as a committed save', async (status) => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('{}', { status }))
    await expect(saveAssessmentDraft('qa', 1, { title: 'Denied QA', items: [], settings: {} })).rejects.toBeInstanceOf(AssessmentHttpError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('retains the original save error when its one reconciliation read fails', async () => {
    const failure = new TypeError('Response lost')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(failure).mockRejectedValueOnce(new TypeError('Still offline'))
    await expect(saveAssessmentDraft('qa', 1, { title: 'Offline QA', items: [], settings: {} })).rejects.toBe(failure)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it.each(['network', 'server'] as const)('does not reconcile a denied PATCH after a %s session-refresh failure', async (failure) => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'CSRF_INVALID' } }), { status: 403 }))
      .mockImplementationOnce(async () => {
        if (failure === 'network') throw new TypeError('Session refresh unavailable')
        return new Response('{}', { status: 503 })
      })
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'qa', revision: 2, document: { title: 'Denied QA', items: [], settings: {} } })))
    await expect(saveAssessmentDraft('qa', 1, { title: 'Denied QA', items: [], settings: {} })).rejects.toThrow()
    expect(fetchMock.mock.calls.map(call => String(call[0]))).toEqual(['/api/v2/admin/assessment/drafts/qa', '/api/v1/auth/session'])
  })

  it('compares distinct Unicode keys independently of insertion order without changing array order', async () => {
    const document: AssessmentDocument = { title: 'Unicode QA', items: [{ id: 'q', type: 'short-answer', prompt: 'QA', answerKey: { '\u00e9': 'one', 'e\u0301': 'two', accepted: ['first', 'second'] } }], settings: {} }
    const reordered: AssessmentDocument = { ...document, items: [{ ...document.items[0], answerKey: { accepted: ['first', 'second'], 'e\u0301': 'two', '\u00e9': 'one' } }] }
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('Response lost'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'qa', revision: 2, document: reordered })))
    expect((await saveAssessmentDraft('qa', 1, document)).revision).toBe(2)
  })

  it('does not reconcile reordered answer arrays as the same submitted document', async () => {
    const failure = new TypeError('Response lost')
    const document: AssessmentDocument = { title: 'Array QA', items: [{ id: 'q', type: 'short-answer', prompt: 'QA', answerKey: { accepted: ['first', 'second'] } }], settings: {} }
    const different = { ...document, items: [{ ...document.items[0], answerKey: { accepted: ['second', 'first'] } }] }
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(failure)
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'qa', revision: 2, document: different })))
    await expect(saveAssessmentDraft('qa', 1, document)).rejects.toBe(failure)
  })
})
