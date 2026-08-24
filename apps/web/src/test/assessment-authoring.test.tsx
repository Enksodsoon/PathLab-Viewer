import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { AssessmentAdminPage } from '../pages/AssessmentAdminPage'
import { AssessmentBuilderPage } from '../pages/AssessmentBuilderPage'

const api = vi.hoisted(() => ({
  createAssessmentDraft: vi.fn(),
  getAssessmentDraft: vi.fn(),
  listAssessmentDrafts: vi.fn(),
  listAssessmentAdministrations: vi.fn(),
  previewAssessmentDraft: vi.fn(),
  publishAssessmentDraft: vi.fn(),
  saveAssessmentDraft: vi.fn(),
}))

vi.mock('../assessment/api', () => api)
vi.mock('../assessment/draftCache', () => ({
  cacheAssessmentDraft: vi.fn(),
  readCachedAssessmentDraft: vi.fn().mockResolvedValue(null),
}))

beforeEach(() => {
  api.listAssessmentAdministrations.mockResolvedValue({ items: [], total: 0 })
  api.listAssessmentDrafts.mockResolvedValue({
    total: 1,
    items: [{
      id: 'draft-1', title: 'Lung pathology', status: 'draft', revision: 1,
      document: { title: 'Lung pathology', items: [], settings: {} },
    }],
  })
  api.getAssessmentDraft.mockResolvedValue({
    id: 'draft-1', title: 'Lung pathology', status: 'draft', revision: 1,
    document: { title: 'Lung pathology', items: [], settings: {} },
  })
  api.saveAssessmentDraft.mockImplementation(async (_id, revision, document) => ({
    id: 'draft-1', title: document.title, status: 'draft', revision: revision + 1, document,
  }))
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

it('presents the PathLab Assessment dashboard and status counts', async () => {
  render(<MemoryRouter><AssessmentAdminPage /></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'My Assessments' })).toBeVisible()
  expect(screen.getByText('Lung pathology')).toBeVisible()
  expect(screen.getByRole('button', { name: 'New assessment' })).toBeVisible()
})

it('adds accessible question cards and exposes publish presets', async () => {
  render(
    <MemoryRouter initialEntries={['/admin/assessments/draft-1']}>
      <Routes>
        <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByRole('heading', { name: 'Lung pathology' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Add multiple choice' }))
  expect(screen.getByRole('group', { name: 'Question 1' })).toBeVisible()
  await userEvent.click(screen.getByRole('tab', { name: 'Settings' }))
  expect(screen.getByRole('radio', { name: /Practice/i })).toBeVisible()
  expect(screen.getByRole('radio', { name: /Formative/i })).toBeVisible()
  expect(screen.getByRole('radio', { name: /Quiz \/ Test/i })).toBeVisible()
})
