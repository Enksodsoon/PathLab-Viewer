import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AssessmentBuilderPage } from '../pages/AssessmentBuilderPage'
import type { AssessmentDraft } from '../assessment/types'

const mocks = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), list: vi.fn(), import: vi.fn(), cache: vi.fn(), read: vi.fn() }))
vi.mock('../assessment/api', async original => ({
  ...await original<typeof import('../assessment/api')>(),
  getAssessmentDraft: mocks.get, saveAssessmentDraft: mocks.save,
  listAssessmentDrafts: mocks.list, importAssessmentQuestions: mocks.import,
}))
vi.mock('../assessment/draftCache', () => ({
  cacheAssessmentDraft: mocks.cache,
  readCachedAssessmentDraft: mocks.read,
}))
vi.mock('../theme/ThemeControl', () => ({ ThemeControl: () => <div /> }))

const initial = { id: 'import-qa', title: 'Original title', status: 'draft', revision: 1,
  document: { title: 'Original title', items: [], settings: {} } }
const question = { id: 'source-q', type: 'short-answer', prompt: 'Synthetic import question', points: '1', required: true }
beforeEach(() => {
  mocks.cache.mockResolvedValue(undefined)
  mocks.read.mockResolvedValue(null)
  mocks.get.mockResolvedValue(initial)
  mocks.save.mockImplementation(async (id, revision, document) => ({ ...initial, id, revision: revision + 1, document }))
  mocks.list.mockResolvedValue({ items: [{ ...initial, id: 'source-qa', title: 'Source', document: { ...initial.document, items: [question] } }] })
  mocks.import.mockResolvedValue({ ...initial, revision: 2, document: { ...initial.document, items: [question] } })
})

it('retains edits made after dismissing a pending import and drains them after its acknowledgment', async () => {
  let finish!: (value: AssessmentDraft) => void
  mocks.import.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  render(<MemoryRouter initialEntries={['/admin/assessments/import-qa']}><Routes>
    <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
  </Routes></MemoryRouter>)
  await screen.findByText('All changes saved')
  vi.useFakeTimers()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Import questions' })) })
  const dialog = screen.getByRole('dialog', { name: 'Import assessment' })
  fireEvent.change(within(dialog).getByRole('combobox', { name: 'Source assessment' }), { target: { value: 'source-qa' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Select all shown' }))
  await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Import selected (1)' })) })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Close import' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'Assessment name' }), { target: { value: 'Edit during import' } })
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  await act(async () => { finish({ ...initial, status: 'draft', revision: 2, document: { ...initial.document, items: [{ ...question, type: 'short-answer' }] } }) })
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue('Edit during import')
  expect(screen.getByRole('group', { name: 'Question 1' })).toBeVisible()
  expect(mocks.save).not.toHaveBeenCalled()
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  expect(mocks.save).toHaveBeenCalledWith('import-qa', 2, expect.objectContaining({ title: 'Edit during import', items: [expect.objectContaining({ id: 'source-q' })] }))
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks() })

it('saves newer edits at the original revision after a pending import fails', async () => {
  let rejectImport!: (error: Error) => void
  mocks.import.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectImport = reject }))
  render(<MemoryRouter initialEntries={['/admin/assessments/import-qa']}><Routes>
    <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
  </Routes></MemoryRouter>)
  await screen.findByText('All changes saved')
  vi.useFakeTimers()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Import questions' })) })
  const dialog = screen.getByRole('dialog', { name: 'Import assessment' })
  fireEvent.change(within(dialog).getByRole('combobox', { name: 'Source assessment' }), { target: { value: 'source-qa' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Select all shown' }))
  await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Import selected (1)' })) })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Close import' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'Assessment name' }), { target: { value: 'Retained after failed import' } })
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  expect(mocks.save).not.toHaveBeenCalled()
  await act(async () => { rejectImport(new Error('Synthetic import unavailable')) })
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  expect(mocks.save).toHaveBeenCalledTimes(1)
  expect(mocks.save).toHaveBeenCalledWith('import-qa', 1, expect.objectContaining({ title: 'Retained after failed import', items: [] }))
  expect(screen.getByText('All changes saved')).toBeVisible()
})

it('ignores import acknowledgment from a draft that is no longer open', async () => {
  let finish!: (value: AssessmentDraft) => void
  mocks.import.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  mocks.get.mockImplementation(async (id: string) => ({ ...initial, id, document: { ...initial.document, title: id === 'second-qa' ? 'Second draft title' : initial.document.title } }))
  render(<MemoryRouter initialEntries={['/admin/assessments/import-qa']}><Routes>
    <Route path="/admin/assessments/:draftId" element={<><Link to="/admin/assessments/second-qa">Open next draft</Link><AssessmentBuilderPage /></>} />
  </Routes></MemoryRouter>)
  await screen.findByText('All changes saved')
  vi.useFakeTimers()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Import questions' })) })
  const dialog = screen.getByRole('dialog', { name: 'Import assessment' })
  fireEvent.change(within(dialog).getByRole('combobox', { name: 'Source assessment' }), { target: { value: 'source-qa' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Select all shown' }))
  await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Import selected (1)' })) })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Close import' }))
  await act(async () => { fireEvent.click(screen.getByRole('link', { name: 'Open next draft' })) })
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue('Second draft title')
  await act(async () => { finish({ ...initial, status: 'draft', revision: 9, document: { ...initial.document, items: [{ ...question, type: 'short-answer' }] } }) })
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue('Second draft title')
  fireEvent.change(screen.getByRole('textbox', { name: 'Assessment name' }), { target: { value: 'Second draft edit' } })
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  expect(mocks.save).toHaveBeenCalledWith('second-qa', 1, expect.objectContaining({ title: 'Second draft edit' }))
})

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
