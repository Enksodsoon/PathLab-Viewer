import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { AssessmentDraft } from '../assessment/types'
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
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks() })

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
