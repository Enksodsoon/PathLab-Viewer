import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { AssessmentDraft } from '../assessment/types'
import { AssessmentHttpError } from '../assessment/api'
import { AssessmentBuilderPage } from '../pages/AssessmentBuilderPage'

const mocks = vi.hoisted(() => ({
  get: vi.fn(), save: vi.fn(), cache: vi.fn(), read: vi.fn(),
}))
vi.mock('../assessment/api', async (original) => ({
  ...await original<typeof import('../assessment/api')>(),
  getAssessmentDraft: mocks.get, saveAssessmentDraft: mocks.save,
}))
vi.mock('../assessment/draftCache', () => ({
  cacheAssessmentDraft: mocks.cache, readCachedAssessmentDraft: mocks.read,
}))
vi.mock('../theme/ThemeControl', () => ({ ThemeControl: () => <div /> }))

const initial: AssessmentDraft = {
  id: 'save-qa', title: 'Synthetic save QA', status: 'draft', revision: 1,
  document: { title: 'Synthetic save QA', items: [], settings: {} },
}
function view() {
  return render(<MemoryRouter initialEntries={['/admin/assessments/save-qa']}><Routes>
    <Route path="/admin/assessments/:draftId" element={<><Link to="/admin/assessments/second-qa">Open second draft</Link><AssessmentBuilderPage /></>} />
  </Routes></MemoryRouter>)
}
function edit(title: string) {
  fireEvent.change(screen.getByRole('textbox', { name: 'Assessment name' }), { target: { value: title } })
}
async function advance() { await act(async () => { await vi.advanceTimersByTimeAsync(750) }) }
beforeEach(() => {
  mocks.get.mockResolvedValue(initial)
  mocks.read.mockResolvedValue(null)
  mocks.cache.mockResolvedValue(undefined)
  mocks.save.mockImplementation(async (id, revision, document) => ({ ...initial, id, revision: revision + 1, document }))
})

it('saves the next draft while a previous draft save remains pending', async () => {
  let acknowledge!: (draft: AssessmentDraft) => void
  mocks.save.mockImplementationOnce(() => new Promise<AssessmentDraft>(resolve => { acknowledge = resolve }))
  mocks.get.mockImplementation(async (id: string) => ({ ...initial, id }))
  view(); await screen.findByText('All changes saved'); vi.useFakeTimers()
  edit('First draft edit'); await advance()
  const oldDocument = mocks.save.mock.calls[0][2]
  await act(async () => { fireEvent.click(screen.getByRole('link', { name: 'Open second draft' })) })
  edit('Second draft edit'); await advance()
  expect(mocks.save).toHaveBeenLastCalledWith('second-qa', 1, expect.objectContaining({ title: 'Second draft edit' }))
  await act(async () => { acknowledge({ ...initial, revision: 10, document: oldDocument }) })
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue('Second draft edit')
  edit('Next second draft edit'); await advance()
  expect(mocks.save).toHaveBeenLastCalledWith('second-qa', 2, expect.objectContaining({ title: 'Next second draft edit' }))
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks(); vi.unstubAllGlobals() })

it('serializes edits behind the pending server revision acknowledgment', async () => {
  let acknowledge!: (draft: AssessmentDraft) => void
  mocks.save.mockImplementationOnce(() => new Promise<AssessmentDraft>(resolve => { acknowledge = resolve }))
  view(); await screen.findByText('All changes saved'); vi.useFakeTimers()
  edit('First edit'); await advance()
  edit('Second edit'); await advance()
  expect(mocks.save).toHaveBeenCalledTimes(1)
  await act(async () => { acknowledge({ ...initial, revision: 2, document: mocks.save.mock.calls[0][2] }) })
  await advance()
  expect(mocks.save).toHaveBeenCalledTimes(2)
  expect(mocks.save).toHaveBeenLastCalledWith('save-qa', 2, expect.objectContaining({ title: 'Second edit' }))
  expect(screen.getByText('All changes saved')).toBeVisible()
})

it('keeps newer edits unsaved until their own acknowledgment', async () => {
  let acknowledge!: (draft: AssessmentDraft) => void
  mocks.save.mockImplementationOnce(() => new Promise<AssessmentDraft>(resolve => { acknowledge = resolve }))
  view(); await screen.findByText('All changes saved'); vi.useFakeTimers()
  edit('First edit'); await advance()
  const firstDocument = mocks.save.mock.calls[0][2]
  edit('Second edit')
  await act(async () => { acknowledge({ ...initial, revision: 2, document: firstDocument }) })
  expect(screen.queryByText('All changes saved')).not.toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue('Second edit')
  await advance()
  expect(mocks.save).toHaveBeenLastCalledWith('save-qa', 2, expect.objectContaining({ title: 'Second edit' }))
  expect(screen.getByText('All changes saved')).toBeVisible()
})

it('does not replace the latest local recovery copy with an older acknowledgment', async () => {
  let acknowledge!: (draft: AssessmentDraft) => void
  mocks.save.mockImplementationOnce(() => new Promise<AssessmentDraft>(resolve => { acknowledge = resolve }))
  view(); await screen.findByText('All changes saved'); vi.useFakeTimers()
  edit('First edit'); await advance()
  const firstDocument = mocks.save.mock.calls[0][2]
  edit('Second edit')
  await act(async () => { acknowledge({ ...initial, revision: 2, document: firstDocument }) })
  expect(mocks.cache.mock.calls.at(-1)?.[0].document.title).toBe('Second edit')
})

it('opens the server draft when local recovery storage is denied', async () => {
  mocks.read.mockRejectedValueOnce(new DOMException('Storage denied', 'SecurityError'))
  view()
  expect(await screen.findByText('All changes saved')).toBeVisible()
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue(initial.document.title)
})

it('retains the load failure when the server draft is unavailable', async () => {
  mocks.get.mockRejectedValueOnce(new Error('Server unavailable'))
  mocks.read.mockRejectedValueOnce(new DOMException('Storage denied', 'SecurityError'))
  view()
  expect(await screen.findByText('Unable to open draft')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Retry' })).toBeVisible()
  expect(mocks.save).not.toHaveBeenCalled()
})

it('retries a temporary server failure without changing the retained draft or revision', async () => {
  mocks.save.mockRejectedValueOnce(new AssessmentHttpError(503, {}))
  view(); await screen.findByText('All changes saved'); vi.useFakeTimers()
  edit('Retained after temporary failure'); await advance()
  expect(screen.getByText('Changes not saved. Try again.')).toBeVisible()
  expect(screen.queryByText('Conflict: reload or duplicate')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry save' }))
  expect(screen.queryByRole('button', { name: 'Retry save' })).not.toBeInTheDocument()
  await advance()
  expect(mocks.save).toHaveBeenLastCalledWith('save-qa', 1, expect.objectContaining({ title: 'Retained after temporary failure' }))
  expect(screen.getByText('All changes saved')).toBeVisible()
})

it.each([
  [401, 'Changes not saved. Sign in again to save.', false],
  [403, 'Changes not saved. You do not have permission to save this draft.', false],
  [404, 'This draft is unavailable. Your changes remain in this tab.', false],
  [409, 'Conflict: reload or duplicate', false],
  [422, 'Changes not saved. Check the questions and settings.', false],
  [429, 'Save paused. Wait a moment, then retry.', true],
] as const)('preserves edits and reports HTTP%s without bypassing the failed boundary', async (status, message, retryable) => {
  mocks.save.mockRejectedValueOnce(new AssessmentHttpError(status, {}))
  view(); await screen.findByText('All changes saved'); vi.useFakeTimers()
  edit('Retained unsaved edit'); await advance()
  expect(screen.getByText(message)).toBeVisible()
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue('Retained unsaved edit')
  expect(Boolean(screen.queryByRole('button', { name: 'Retry save' }))).toBe(retryable)
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })
  expect(mocks.save).toHaveBeenCalledTimes(1)
  expect(screen.queryByText('All changes saved')).not.toBeInTheDocument()
})

it('clears retry from a failed draft when another draft loads', async () => {
  mocks.save.mockRejectedValueOnce(new TypeError('Synthetic network loss'))
  mocks.get.mockImplementation(async (id: string) => ({ ...initial, id }))
  view(); await screen.findByText('All changes saved'); vi.useFakeTimers()
  edit('Retained first draft edit'); await advance()
  expect(screen.getByRole('button', { name: 'Retry save' })).toBeVisible()
  await act(async () => { fireEvent.click(screen.getByRole('link', { name: 'Open second draft' })) })
  expect(screen.queryByRole('button', { name: 'Retry save' })).not.toBeInTheDocument()
  expect(screen.getByText('All changes saved')).toBeVisible()
  edit('Second draft edit'); await advance()
  expect(mocks.save).toHaveBeenLastCalledWith('second-qa', 1, expect.objectContaining({ title: 'Second draft edit' }))
})

it('reports an expired session raised by the actual CSRF refresh path', async () => {
  const actual = await vi.importActual<typeof import('../assessment/api')>('../assessment/api')
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'CSRF_INVALID' } }), { status: 403 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: 'AUTH_REQUIRED' } }), { status: 401 }))
  vi.stubGlobal('fetch', fetchMock)
  mocks.save.mockImplementation(actual.saveAssessmentDraft)
  view(); await screen.findByText('All changes saved'); vi.useFakeTimers()
  edit('Retained expired-session edit'); await advance()
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(screen.getByText('Changes not saved. Sign in again to save.')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Retry save' })).not.toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue('Retained expired-session edit')
})
