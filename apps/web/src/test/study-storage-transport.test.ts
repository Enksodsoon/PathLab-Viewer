import { afterEach, expect, it, vi } from 'vitest'
import { getStudySession, submitStudyTask, withdrawStudy } from '../study/api'
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
it('retains server-issued Study CSRF in memory when session storage is blocked', async () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('Denied') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Denied') })
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new DOMException('Denied') })
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: 'issued-token' }), { status: 200 })).mockImplementation(async () => new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', fetch)
  await getStudySession()
  await submitStudyTask('one', { selectedOption: 'A' })
  expect(fetch.mock.calls[1][1].headers['X-Study-CSRF']).toBe('issued-token')
  await withdrawStudy()
  await submitStudyTask('one', { selectedOption: 'A' })
  expect(fetch.mock.calls[3][1].headers['X-Study-CSRF']).toBe('')
})
