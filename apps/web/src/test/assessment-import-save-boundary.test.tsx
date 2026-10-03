import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AssessmentBuilderPage } from '../pages/AssessmentBuilderPage'

const mocks = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), list: vi.fn(), import: vi.fn() }))
vi.mock('../assessment/api', async original => ({
  ...await original<typeof import('../assessment/api')>(),
  getAssessmentDraft: mocks.get, saveAssessmentDraft: mocks.save,
  listAssessmentDrafts: mocks.list, importAssessmentQuestions: mocks.import,
}))
vi.mock('../assessment/draftCache', () => ({
  cacheAssessmentDraft: vi.fn().mockResolvedValue(undefined),
  readCachedAssessmentDraft: vi.fn().mockResolvedValue(null),
}))
vi.mock('../theme/ThemeControl', () => ({ ThemeControl: () => <div /> }))

const initial = { id: 'import-qa', title: 'Original title', status: 'draft', revision: 1,
  document: { title: 'Original title', items: [], settings: {} } }
const question = { id: 'source-q', type: 'short-answer', prompt: 'Synthetic import question', points: '1', required: true }
beforeEach(() => {
  mocks.get.mockResolvedValue(initial)
  mocks.save.mockImplementation(async (id, revision, document) => ({ ...initial, id, revision: revision + 1, document }))
  mocks.list.mockResolvedValue({ items: [{ ...initial, id: 'source-qa', title: 'Source', document: { ...initial.document, items: [question] } }] })
  mocks.import.mockResolvedValue({ ...initial, revision: 2, document: { ...initial.document, items: [question] } })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks() })

it('preserves unsaved edits when import is selected before autosave runs', async () => {
  render(<MemoryRouter initialEntries={['/admin/assessments/import-qa']}><Routes>
    <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
  </Routes></MemoryRouter>)
  await screen.findByText('All changes saved')
  vi.useFakeTimers()
  fireEvent.change(screen.getByRole('textbox', { name: 'Assessment name' }), { target: { value: 'Unsaved local title' } })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Import questions' })) })
  const dialog = screen.getByRole('dialog', { name: 'Import assessment' })
  fireEvent.change(within(dialog).getByRole('combobox', { name: 'Source assessment' }), { target: { value: 'source-qa' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Select all shown' }))
  await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Import selected (1)' })) })
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue('Unsaved local title')
  expect(mocks.import).not.toHaveBeenCalled()
  expect(within(dialog).getByRole('button', { name: 'Import selected (1)' })).toBeDisabled()
  expect(within(dialog).getByText('Save your changes before importing questions.')).toBeVisible()
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  expect(mocks.save).toHaveBeenCalledWith('import-qa', 1, expect.objectContaining({ title: 'Unsaved local title' }))
  mocks.import.mockResolvedValueOnce({ ...initial, revision: 3, document: { ...initial.document, title: 'Unsaved local title', items: [question] } })
  expect(within(dialog).getByRole('button', { name: 'Import selected (1)' })).toBeEnabled()
  await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Import selected (1)' })) })
  expect(mocks.import).toHaveBeenCalledWith('import-qa', 'source-qa', ['source-q'], 2)
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue('Unsaved local title')
  expect(screen.queryByRole('dialog', { name: 'Import assessment' })).not.toBeInTheDocument()
})
