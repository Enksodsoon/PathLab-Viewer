import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { AssessmentDraft } from '../assessment/types'
import { AssessmentBuilderPage } from '../pages/AssessmentBuilderPage'

const mocks = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), cache: vi.fn(), read: vi.fn() }))
vi.mock('../assessment/api', async original => ({
  ...await original<typeof import('../assessment/api')>(),
  getAssessmentDraft: mocks.get, saveAssessmentDraft: mocks.save,
}))
vi.mock('../assessment/draftCache', () => ({ cacheAssessmentDraft: mocks.cache, readCachedAssessmentDraft: mocks.read }))
vi.mock('../theme/ThemeControl', () => ({ ThemeControl: () => <div /> }))

const initial: AssessmentDraft = { id: 'recovery-qa', title: 'Synthetic recovery QA', status: 'draft', revision: 1, document: { title: 'Synthetic recovery QA', items: [], settings: {} } }
function view() {
  return render(<MemoryRouter initialEntries={['/admin/assessments/recovery-qa']}><Routes>
    <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
  </Routes></MemoryRouter>)
}
beforeEach(() => {
  mocks.get.mockResolvedValue(initial)
  mocks.read.mockResolvedValue(null)
  mocks.cache.mockResolvedValue(undefined)
  mocks.save.mockImplementation(async (id, revision, document) => ({ ...initial, id, revision: revision + 1, document }))
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks() })

it('acknowledges a successful server save when local recovery writes reject', async () => {
  mocks.cache.mockRejectedValue(new DOMException('Synthetic storage denial', 'SecurityError'))
  view(); await screen.findByText('All changes saved'); vi.useFakeTimers()
  fireEvent.change(screen.getByRole('textbox', { name: 'Assessment name' }), { target: { value: 'Server saved edit' } })
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  expect(mocks.save).toHaveBeenCalledTimes(1)
  expect(screen.getByText('All changes saved')).toBeVisible()
})

it('recovers locally cached edits after failed save and reload at the unchanged server revision', async () => {
  let cached: AssessmentDraft | null = null
  mocks.cache.mockImplementation(async (draft: AssessmentDraft) => { cached = draft })
  mocks.read.mockImplementation(async () => cached)
  mocks.save.mockRejectedValue(new Error('Synthetic server unavailable'))
  const first = view(); await screen.findByText('All changes saved'); vi.useFakeTimers()
  fireEvent.change(screen.getByRole('textbox', { name: 'Assessment name' }), { target: { value: 'Locally retained edit' } })
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  expect(screen.getByText('Conflict: reload or duplicate')).toBeVisible()
  expect(mocks.cache.mock.calls[0][0].revision).toBe(initial.revision)
  first.unmount(); vi.useRealTimers(); view()
  await screen.findByRole('textbox', { name: 'Assessment name' })
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue('Locally retained edit')
})

it('does not overwrite a newer server revision with older cached edits', async () => {
  mocks.read.mockResolvedValue({ ...initial, revision: 0, document: { ...initial.document, title: 'Older cached edit' } })
  view()
  await screen.findByText('All changes saved')
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue(initial.document.title)
  expect(mocks.save).not.toHaveBeenCalled()
})
