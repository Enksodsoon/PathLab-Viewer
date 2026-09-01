import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { AssessmentAdminPage } from '../pages/AssessmentAdminPage'
import { AssessmentBuilderPage } from '../pages/AssessmentBuilderPage'
import { AssessmentReportPage } from '../pages/AssessmentReportPage'

const api = vi.hoisted(() => ({
  archiveAssessmentDraft: vi.fn(),
  createAssessmentDraft: vi.fn(),
  duplicateAssessmentDraft: vi.fn(),
  getAssessmentCourse: vi.fn(),
  getAssessmentDraft: vi.fn(),
  getAssessmentMetadata: vi.fn(),
  getAssessmentResults: vi.fn(),
  gradeAssessmentResponse: vi.fn(),
  importAssessmentQuestions: vi.fn(),
  listAssessmentDrafts: vi.fn(),
  listAssessmentAdministrations: vi.fn(),
  listAssessmentCourses: vi.fn(),
  previewAssessmentDraft: vi.fn(),
  publishAssessmentDraft: vi.fn(),
  restoreAssessmentDraft: vi.fn(),
  saveAssessmentDraft: vi.fn(),
  setAssessmentAdministrationStatus: vi.fn(),
}))

vi.mock('../assessment/api', () => api)
vi.mock('../theme/ThemeControl', () => ({
  ThemeControl: () => <div aria-label="Theme preference" />,
}))
vi.mock('../assessment/draftCache', () => ({
  cacheAssessmentDraft: vi.fn(),
  readCachedAssessmentDraft: vi.fn().mockResolvedValue(null),
}))
beforeEach(() => {
  api.getAssessmentMetadata.mockResolvedValue(undefined)
  api.listAssessmentCourses.mockResolvedValue({ items: [{ id: 'course-1', name: 'Thoracic Pathology', courseCode: 'PATH 301', semester: '1', academicYear: '2027', iconKey: 'general', scoringMethod: 'percentage', description: null, opensAt: null, closesAt: null, status: 'active', rosterCount: 10, classCount: 1 }], total: 1 })
  api.getAssessmentCourse.mockResolvedValue({ id: 'course-1', name: 'Thoracic Pathology', courseCode: 'PATH 301', semester: '1', academicYear: '2027', iconKey: 'general', scoringMethod: 'percentage', description: null, opensAt: null, closesAt: null, status: 'active', rosterCount: 10, classCount: 1, classes: [{ id: 'class-1', name: 'Demo cohort', sectionCode: 'DEMO-A' }] })
  api.listAssessmentAdministrations.mockResolvedValue({ items: [], total: 0 })
  api.previewAssessmentDraft.mockResolvedValue({ learnerManifest: { title: 'Lung pathology', items: [], settings: {} }, checksum: 'preview' })
  api.setAssessmentAdministrationStatus.mockResolvedValue({ id: 'administration-1', status: 'closed' })
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
  api.importAssessmentQuestions.mockImplementation(async (_id, _sourceId, _itemIds, revision) => ({
    id: 'draft-1', title: 'Lung pathology', status: 'draft', revision: revision + 1,
    document: { title: 'Lung pathology', items: [], settings: {} },
  }))
  api.restoreAssessmentDraft.mockImplementation(async (id) => ({
    id, title: 'Archived assessment', status: 'draft', revision: 1,
    document: { title: 'Archived assessment', items: [], settings: {} },
  }))
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
})

it('presents the PathLab Assessment dashboard and status counts', async () => {
  const { container } = render(<MemoryRouter initialEntries={['/admin/assessments']}><Routes>
    <Route path="/admin/assessments" element={<AssessmentAdminPage />} />
    <Route path="/admin/assessments/:draftId" element={<div>Assessment responses</div>} />
  </Routes></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'My Assessments' })).toBeVisible()
  const workspace = screen.getByRole('navigation', { name: 'Assessment workspace' })
  expect(within(workspace).getAllByRole('link').map((link) => link.textContent)).toEqual(['Courses', 'Assessments'])
  expect(within(workspace).queryByRole('link', { name: 'Results' })).not.toBeInTheDocument()
  expect(screen.getByText('Lung pathology')).toBeVisible()
  expect(screen.getByRole('button', { name: 'New assessment' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'New assessment' })).toHaveTextContent('')
  expect(screen.getByRole('button', { name: /Sort by Assessment/ })).toBeVisible()
  expect(screen.getByRole('button', { name: /Sort by Course/ })).toBeVisible()
  expect(screen.getByRole('button', { name: /Sort by Class/ })).toBeVisible()
  expect(screen.getByRole('button', { name: /Sort by Status/ })).toBeVisible()
  expect(screen.getByRole('button', { name: /Sort by Progress/ })).toBeVisible()
  expect(screen.getByRole('button', { name: /Sort by Modified/ })).toBeVisible()
  expect(screen.getByRole('columnheader', { name: 'Course' })).toBeVisible()
  expect(screen.getByRole('columnheader', { name: 'Class' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'New assessment' }))
  expect(screen.getByRole('dialog', { name: 'Choose where it belongs' })).toBeVisible()
  expect(screen.getByRole('combobox', { name: 'Course' })).toBeVisible()
  expect(screen.getByRole('combobox', { name: 'Class' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Duplicate Lung pathology, revision 1' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Archive Lung pathology, revision 1' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'View report for Lung pathology' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'View report for Lung pathology' }))
  expect(screen.getByText('Assessment responses')).toBeVisible()
  expect(container.querySelector('.assessment-preview-backdrop')).not.toBeInTheDocument()
})

it('presents a dedicated visual report with question and student views', async () => {
  api.getAssessmentDraft.mockResolvedValue({
    id: 'draft-1', title: 'Lung pathology', status: 'draft', revision: 1,
    document: { title: 'Lung pathology', items: [{ id: 'question-1', type: 'multiple-choice', prompt: 'Which diagnosis is most likely?', points: '7' }], settings: {} },
  })
  api.listAssessmentAdministrations.mockResolvedValue({ items: [{
    id: 'administration-1', draftId: 'draft-1', publicId: 'public-1', title: 'Lung pathology',
    version: 1, mode: 'formative', status: 'closed', responses: 1, expectedParticipants: 1, completedParticipants: 1, createdAt: '2026-08-24T00:00:00Z',
  }], total: 1 })
  api.getAssessmentResults.mockResolvedValue({
    administration: { id: 'administration-1', mode: 'formative', status: 'closed' },
    summary: { responses: 1, averagePoints: '6', completionRate: '1', needsGrading: 0, questions: { 'question-1': { responseCount: 1, scoredCount: 1, averagePoints: '6' } } },
    individuals: { total: 1, items: [{ attemptId: 'attempt-1', displayName: 'Anan Charoen', status: 'graded', scoreVersion: 1, points: '8.167', maximumPoints: '11.666666666666666', breakdown: { 'question-1': '6' }, responses: {} }] },
  })

  render(<MemoryRouter initialEntries={['/admin/assessments/draft-1/report']}><Routes>
    <Route path="/admin/assessments/:draftId/report" element={<AssessmentReportPage />} />
  </Routes></MemoryRouter>)

  expect(await screen.findByRole('heading', { name: 'Lung pathology' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Summary' })).toHaveAttribute('aria-current', 'page')
  expect(await screen.findByRole('heading', { name: 'Score distribution' })).toBeVisible()
  expect(screen.getByRole('button', { name: '60-79%: 1 learners' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByText('8.17 / 11.67')).toBeVisible()
  expect(screen.queryByRole('complementary', { name: 'Learners needing support' })).not.toBeInTheDocument()
  expect(screen.getByText('Closed')).toBeVisible()
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Response views' })).getByRole('button', { name: 'Questions' }))
  expect(screen.getByRole('heading', { name: 'Which diagnosis is most likely?' })).toBeVisible()
  expect(screen.getByText('7 points')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Question' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'View question' })).not.toBeInTheDocument()
  expect(screen.getByText('Excel').closest('a, button')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Visual' })).toHaveAttribute('download', 'lung-pathology-visual-report.svg')

  expect(screen.getByRole('button', { name: 'Questions' })).toBeVisible()
  expect(screen.getByRole('button', { name: /Needs grading/ })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Individuals' }))
  expect(screen.getByRole('heading', { name: 'Individual response' })).toBeVisible()
  expect(screen.getAllByText('Anan Charoen')).toHaveLength(2)
  expect(screen.getByText('70% score')).toBeVisible()
})

it('renders the shared report inside the builder Responses tab', async () => {
  api.listAssessmentAdministrations.mockResolvedValue({ items: [{
    id: 'administration-1', draftId: 'draft-1', publicId: 'public-1', title: 'Lung pathology',
    version: 1, mode: 'formative', status: 'closed', responses: 1, expectedParticipants: 1, completedParticipants: 1, createdAt: '2026-08-24T00:00:00Z',
  }], total: 1 })
  api.getAssessmentResults.mockResolvedValue({
    administration: { id: 'administration-1', mode: 'formative', status: 'closed' },
    summary: { responses: 1, averagePoints: '1', completionRate: '1', needsGrading: 0, questions: {} },
    individuals: { total: 1, items: [{ attemptId: 'attempt-1', displayName: 'Anan Charoen', status: 'graded', scoreVersion: 1, points: '1', maximumPoints: '1', breakdown: {}, responses: {} }] },
  })

  render(<MemoryRouter initialEntries={['/admin/assessments/draft-1?tab=responses&classId=class-1&courseId=course-1']}><Routes>
    <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
  </Routes></MemoryRouter>)

  expect(await screen.findByRole('tab', { name: 'Responses' })).toHaveAttribute('aria-selected', 'true')
  expect(await screen.findByRole('heading', { name: 'Lung pathology' })).toBeVisible()
  expect(await screen.findByRole('heading', { name: 'Score distribution' })).toBeVisible()
  expect(screen.queryByText('Results appear after a published administration receives submissions.')).not.toBeInTheDocument()
  expect(screen.queryByText('Assessment report')).not.toBeInTheDocument()
})

it('keeps published report questions separate from newer draft edits and filters learners', async () => {
  api.getAssessmentDraft.mockResolvedValue({
    id: 'draft-1', title: 'Versioned assessment', status: 'draft', revision: 3,
    document: { title: 'Versioned assessment', items: [{ id: 'draft-question', type: 'short-answer', prompt: 'New draft-only question', points: '1' }], settings: {} },
  })
  api.listAssessmentAdministrations.mockResolvedValue({ items: [{
    id: 'administration-1', draftId: 'draft-1', publicId: 'public-1', title: 'Versioned assessment',
    version: 1, mode: 'quiz', status: 'closed', responses: 2, expectedParticipants: 2, completedParticipants: 2, createdAt: '2026-08-24T00:00:00Z',
  }], total: 1 })
  api.getAssessmentMetadata.mockResolvedValue({
    manifest: { title: 'Versioned assessment', items: [{ id: 'published-question', type: 'multiple-choice', prompt: 'Published question', points: '2', options: [{ id: 'a', label: 'A' }] }], settings: {} },
  })
  api.getAssessmentResults.mockResolvedValue({
    administration: { id: 'administration-1', mode: 'quiz', status: 'closed' },
    summary: { responses: 2, averagePoints: '1', completionRate: '1', needsGrading: 0, questions: { 'published-question': { responseCount: 2, scoredCount: 2, averagePoints: '1' } } },
    individuals: { total: 2, items: [
      { attemptId: 'attempt-1', displayName: 'Anan Charoen', status: 'graded', scoreVersion: 1, points: '1', maximumPoints: '2', breakdown: { 'published-question': '1' }, responses: {} },
      { attemptId: 'attempt-2', displayName: 'Zain Osman', status: 'graded', scoreVersion: 1, points: '2', maximumPoints: '2', breakdown: { 'published-question': '2' }, responses: {} },
    ] },
  })

  render(<MemoryRouter initialEntries={['/admin/assessments/draft-1/report']}><Routes><Route path="/admin/assessments/:draftId/report" element={<AssessmentReportPage />} /></Routes></MemoryRouter>)

  expect(await screen.findByText('Showing published version 1 with 1 questions. The editable draft currently has 1 questions.')).toBeVisible()
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Response views' })).getByRole('button', { name: 'Questions' }))
  expect(screen.getByRole('heading', { name: 'Published question' })).toBeVisible()
  expect(screen.queryByText('New draft-only question')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Individuals' }))
  await userEvent.type(screen.getByRole('searchbox', { name: 'Search learners' }), 'Zain')
  expect(screen.getByRole('combobox', { name: 'Select learner' })).toHaveTextContent('Zain Osman')
  expect(screen.getByRole('combobox', { name: 'Select learner' })).not.toHaveTextContent('Anan Charoen')
})

it('renders a visual summary for every supported assessment item type', async () => {
  const items = [
    { id: 'mc', type: 'multiple-choice' as const, prompt: 'Choose one diagnosis', points: '1', options: [{ id: 'a', label: 'Adenocarcinoma' }], answerKey: { optionIds: ['a'] } },
    { id: 'checks', type: 'checkboxes' as const, prompt: 'Choose every feature', points: '2', options: [{ id: 'b', label: 'Glands' }, { id: 'c', label: 'Mucin' }], answerKey: { optionIds: ['b', 'c'] } },
    { id: 'short', type: 'short-answer' as const, prompt: 'Give the diagnosis', points: '1' },
    { id: 'paragraph', type: 'paragraph' as const, prompt: 'Explain the morphology', points: '2', manual: true },
    { id: 'field', type: 'diagnostic-field' as const, prompt: 'Mark the invasive focus', points: '1' },
    { id: 'info', type: 'information' as const, prompt: 'Review the reference image' },
  ]
  api.getAssessmentDraft.mockResolvedValue({ id: 'draft-1', title: 'Mixed format report', status: 'draft', revision: 1, document: { title: 'Mixed format report', items, settings: {} } })
  api.listAssessmentAdministrations.mockResolvedValue({ items: [{ id: 'administration-1', draftId: 'draft-1', publicId: 'public-1', title: 'Mixed format report', version: 1, mode: 'quiz', status: 'closed', responses: 2, expectedParticipants: 2, completedParticipants: 2, createdAt: '2026-08-24T00:00:00Z' }], total: 1 })
  api.getAssessmentResults.mockResolvedValue({
    administration: { id: 'administration-1', mode: 'quiz', status: 'closed' },
    summary: { responses: 2, averagePoints: '5', completionRate: '1', needsGrading: 1, questions: {
      mc: { responseCount: 2, scoredCount: 2, averagePoints: '1' }, checks: { responseCount: 2, scoredCount: 2, averagePoints: '1.5' }, short: { responseCount: 2, scoredCount: 2, averagePoints: '1' }, paragraph: { responseCount: 2, scoredCount: 1, averagePoints: '1' }, field: { responseCount: 2, scoredCount: 2, averagePoints: '.5', spatialHeatmap: { width: 2, height: 2, counts: [[0, 1], [2, 0]] } }, info: { responseCount: 0, scoredCount: 0, averagePoints: '0' },
    } },
    individuals: { total: 2, items: [
      { attemptId: 'a1', displayName: 'Anan Charoen', status: 'graded', scoreVersion: 1, points: '6', maximumPoints: '7', breakdown: { mc: '1', checks: '2', short: '1', paragraph: '1', field: '1' }, responses: { mc: { optionId: 'a' }, checks: { optionIds: ['b', 'c'] }, short: { text: 'Adenocarcinoma' }, paragraph: { text: 'Invasive glands' }, field: { kind: 'point', x: .5, y: .5 } } },
      { attemptId: 'a2', displayName: 'Arthit Saelim', status: 'needs_grading', scoreVersion: 1, points: '4', maximumPoints: '7', breakdown: { mc: '1', checks: '1', short: '1', paragraph: null, field: '1' }, responses: { mc: { optionId: 'a' }, checks: { optionIds: ['b'] }, short: { text: 'Adenocarcinoma' }, paragraph: { text: 'Desmoplasia' }, field: { kind: 'rectangle', x: .2, y: .2, width: .3, height: .3 } } },
    ] },
  })

  render(<MemoryRouter initialEntries={['/admin/assessments/draft-1/report']}><Routes><Route path="/admin/assessments/:draftId/report" element={<AssessmentReportPage />} /></Routes></MemoryRouter>)

  expect(await screen.findByRole('heading', { name: 'Mixed format report' })).toBeVisible()
  await userEvent.click(within(screen.getByRole('navigation', { name: 'Response views' })).getByRole('button', { name: 'Questions' }))
  expect(screen.getByRole('list', { name: 'Answer distribution for question 1' })).toBeVisible()
  expect(screen.getByRole('list', { name: 'Answer distribution for question 2' })).toBeVisible()
  expect(screen.getByRole('list', { name: 'Text responses for question 3' })).toBeVisible()
  expect(screen.getByRole('list', { name: 'Text responses for question 4' })).toBeVisible()
  expect(screen.getAllByText('Manual review').length).toBeGreaterThanOrEqual(2)
  expect(document.querySelector('.assessment-response-text-chart')).not.toBeInTheDocument()
  expect(screen.getByRole('img', { name: 'Spatial response heatmap for question 5' })).toBeVisible()
  expect(screen.queryByText('Reference content shown to learners. It has no score or response chart.')).not.toBeInTheDocument()
})

it('renames, previews, and changes an assessment status from the dashboard', async () => {
  api.previewAssessmentDraft.mockResolvedValue({ learnerManifest: {
    title: 'Thoracic Pathology Diagnostic Assessment — Long Demo Title',
    items: [
      { id: 'item-1', type: 'multiple-choice', prompt: 'Which diagnosis best fits invasive malignant glands with desmoplasia?', options: [{ id: 'option-1', label: 'Pulmonary adenocarcinoma with a deliberately long learner-facing option' }] },
      { id: 'item-2', type: 'paragraph', prompt: 'Describe the morphology' },
    ],
    settings: {},
  }, checksum: 'preview' })
  api.listAssessmentAdministrations.mockResolvedValue({ items: [{
    id: 'administration-1', draftId: 'draft-1', publicId: 'public-1', title: 'Lung pathology',
    version: 1, mode: 'formative', status: 'open', responses: 0, expectedParticipants: 20, completedParticipants: 5, createdAt: '2026-08-24T00:00:00Z',
  }], total: 1 })
  render(<MemoryRouter><AssessmentAdminPage /></MemoryRouter>)
  expect(await screen.findByRole('combobox', { name: 'Status for Lung pathology' })).toHaveValue('open')
  expect(screen.getByRole('combobox', { name: 'Status for Lung pathology' })).toHaveClass('assessment-status--open')
  expect(screen.getByText('0 questions · version 1')).toBeVisible()

  await userEvent.click(screen.getByRole('button', { name: 'Rename Lung pathology' }))
  const name = screen.getByRole('textbox', { name: 'Rename Lung pathology' })
  await userEvent.clear(name)
  await userEvent.type(name, 'Thoracic pathology')
  await userEvent.click(screen.getByRole('button', { name: 'Save assessment name' }))
  expect(api.saveAssessmentDraft).toHaveBeenCalledWith('draft-1', 1, expect.objectContaining({ title: 'Thoracic pathology' }))
  expect(await screen.findByText('Thoracic pathology')).toBeVisible()

  await userEvent.click(screen.getByRole('button', { name: 'Preview Thoracic pathology' }))
  expect(await screen.findByRole('dialog', { name: 'Learner preview' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Which diagnosis best fits invasive malignant glands with desmoplasia?' })).toBeVisible()
  expect(screen.getByText('Pulmonary adenocarcinoma with a deliberately long learner-facing option')).toBeVisible()
  const choice = screen.getByRole('radio')
  expect(choice).toBeEnabled()
  await userEvent.click(choice)
  expect(choice).toBeChecked()
  const paragraph = screen.getByRole('textbox', { name: 'Paragraph answer preview' })
  await userEvent.type(paragraph, 'Irregular glands with desmoplasia')
  expect(paragraph).toHaveValue('Irregular glands with desmoplasia')
  expect(screen.queryByRole('button', { name: /submit/i })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Reset preview answers' }))
  expect(screen.getByRole('radio')).not.toBeChecked()
  expect(screen.getByRole('textbox', { name: 'Paragraph answer preview' })).toHaveValue('')
  const closePreview = screen.getByRole('button', { name: 'Close preview' })
  expect(closePreview).toHaveTextContent('')
  await userEvent.click(closePreview)

  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Status for Thoracic pathology' }), 'closed')
  expect(api.setAssessmentAdministrationStatus).toHaveBeenCalledWith('administration-1', 'open', 'closed')
  expect(await screen.findByText('Assessment status changed to closed.')).toBeVisible()
})

it('keeps archived assessments read-only until they are restored', async () => {
  api.listAssessmentDrafts.mockResolvedValue({ total: 1, items: [{
    id: 'archived-1', title: 'Archived assessment', status: 'archived', revision: 1,
    document: { title: 'Archived assessment', items: [], settings: {} },
  }] })
  render(<MemoryRouter><AssessmentAdminPage /></MemoryRouter>)

  expect(await screen.findByRole('button', { name: /Archived assessment.*0 questions.*version 0/ })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Show archived assessments' })).toHaveTextContent('Archived1')
  expect(screen.getByRole('button', { name: 'Rename Archived assessment' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Preview Archived assessment' })).toBeDisabled()
  expect(screen.getByRole('button', { name: /Duplicate Archived assessment/ })).toBeDisabled()
  expect(screen.getByRole('combobox', { name: 'Status for Archived assessment' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Restore Archived assessment' }))
  expect(api.restoreAssessmentDraft).toHaveBeenCalledWith('archived-1')
  expect(await screen.findByText('Archived assessment restored to Draft.')).toBeVisible()
  expect(screen.getByRole('button', { name: /Archived assessment.*0 questions.*version 0/ })).toBeEnabled()
})

it('derives live metric counts from each assessment latest lifecycle state', async () => {
  api.listAssessmentDrafts.mockResolvedValue({
    total: 3,
    items: [
      { id: 'draft-1', title: 'Closed assessment', status: 'draft', revision: 5, document: { title: 'Closed assessment', items: [], settings: {} } },
      { id: 'draft-2', title: 'Draft assessment', status: 'draft', revision: 2, document: { title: 'Draft assessment', items: [], settings: {} } },
      { id: 'draft-3', title: 'New assessment', status: 'draft', revision: 1, document: { title: 'New assessment', items: [], settings: {} } },
    ],
  })
  api.listAssessmentAdministrations.mockResolvedValue({ items: [{
    id: 'administration-1', draftId: 'draft-1', publicId: 'public-1', title: 'Closed assessment',
    version: 2, mode: 'formative', status: 'closed', responses: 4, expectedParticipants: 5, completedParticipants: 4, createdAt: '2026-08-24T00:00:00Z',
  }], total: 1 })

  render(<MemoryRouter><AssessmentAdminPage /></MemoryRouter>)
  expect(await screen.findByRole('combobox', { name: 'Status for Closed assessment' })).toHaveValue('closed')
  const metrics = screen.getByRole('region', { name: 'Assessment status' })
  const metric = (label: string) => within(metrics).getByText(label).closest('button')
  expect(metric('Drafts')).toHaveTextContent('2')
  expect(metric('Open')).toHaveTextContent('0')
  expect(metric('Closed')).toHaveTextContent('1')
  expect(metric('Archived')).toHaveTextContent('0')
  expect(within(metrics).queryByText('Total responses')).not.toBeInTheDocument()
  expect(screen.getByRole('img', { name: '4 of 5 learners completed, 80%' })).toBeVisible()
  expect(screen.queryByText('4 of 5')).not.toBeInTheDocument()
  expect(screen.getByText('0 questions · version 2')).toBeVisible()
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
  expect(screen.getByRole('textbox', { name: 'Assessment name' })).toHaveValue('Lung pathology')
  expect(screen.getByRole('textbox', { name: 'Assessment description' })).toBeVisible()
  expect(screen.queryByRole('tab', { name: 'Description' })).not.toBeInTheDocument()
  await userEvent.click(screen.getAllByRole('button', { name: 'Add question' })[0])
  await userEvent.click(screen.getByRole('button', { name: 'Add multiple choice' }))
  expect(screen.getByRole('group', { name: 'Question 1' })).toBeVisible()
  api.previewAssessmentDraft.mockRejectedValueOnce(new Error('Draft validation failed'))
  await userEvent.click(screen.getByRole('button', { name: 'Assignment preview' }))
  expect(await screen.findByRole('dialog', { name: 'Learner preview' })).toBeVisible()
  expect(screen.getByRole('status')).toHaveTextContent('Previewing the current draft')
  await userEvent.click(screen.getByRole('button', { name: 'Close preview' }))
  await userEvent.click(screen.getByRole('tab', { name: 'Settings' }))
  expect(screen.getByRole('radio', { name: /Practice/i })).toBeVisible()
  expect(screen.getByRole('radio', { name: /Formative/i })).toBeVisible()
  expect(screen.getByRole('radio', { name: /Quiz \/ Test/i })).toBeVisible()
})

it('previews the current authored sequence instead of a stale server manifest', async () => {
  const currentDocument = {
    schema: 'pathlab.assessment/2' as const,
    title: 'Current authoring draft',
    description: 'Current description',
    presentation: { preset: 'standard' as const, showProgress: true, showSectionTitles: true },
    settings: { mode: 'formative' as const, shuffleQuestions: true },
    sections: [{
      id: 'section-current',
      title: 'Current section',
      description: 'Current section description',
      items: [{
        id: 'current-first', type: 'dropdown' as const, prompt: 'Current first question', required: true, points: '1',
        options: [{ id: 'current-a', label: 'Current answer A' }, { id: 'current-b', label: 'Current answer B' }],
        answerKey: { optionIds: ['current-a'] },
      }, {
        id: 'current-second', type: 'multiple-choice' as const, prompt: 'Current second question', required: false, points: '1',
        options: [{ id: 'second-a', label: 'Second answer A' }, { id: 'second-b', label: 'Second answer B' }],
        answerKey: { optionIds: ['second-a'] },
      }],
    }],
  }
  api.getAssessmentDraft.mockResolvedValue({ id: 'draft-1', title: currentDocument.title, status: 'draft', revision: 3, document: currentDocument })
  api.previewAssessmentDraft.mockResolvedValue({
    learnerManifest: { ...currentDocument, sections: [{ ...currentDocument.sections[0], items: [{ ...currentDocument.sections[0].items[0], id: 'stale-question', prompt: 'Stale server question' }] }] },
    checksum: 'stale-preview',
  })

  render(<MemoryRouter initialEntries={['/admin/assessments/draft-1']}><Routes>
    <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
  </Routes></MemoryRouter>)

  expect(await screen.findByRole('heading', { name: 'Current authoring draft' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Assignment preview' }))
  expect(await screen.findByRole('heading', { name: 'Current first question' })).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Stale server question' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
  expect(screen.getByRole('heading', { name: 'Current second question' })).toBeVisible()
})

it('keeps a 100-question assessment focused on one editable card at a time', async () => {
  const items = Array.from({ length: 100 }, (_, index) => ({
    id: `question-${index + 1}`,
    type: 'multiple-choice' as const,
    prompt: `Question ${index + 1}`,
    points: '1',
    required: false,
    options: ['Option A', 'Option B'],
    answerKey: ['Option A'],
    feedback: '',
  }))
  api.getAssessmentDraft.mockResolvedValue({
    id: 'draft-1', title: 'Large assessment', status: 'draft', revision: 1,
    document: { title: 'Large assessment', items, settings: {} },
  })

  const { container } = render(
    <MemoryRouter initialEntries={['/admin/assessments/draft-1']}>
      <Routes>
        <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
      </Routes>
    </MemoryRouter>,
  )

  expect(await screen.findByRole('heading', { name: 'Large assessment' })).toBeVisible()
  expect(container.querySelector('.assessment-studio-meta')).toHaveTextContent('100 questions')
  expect(container.querySelectorAll('.assessment-question-card')).toHaveLength(100)
  expect(screen.getByRole('group', { name: 'Question 1' })).toHaveAttribute('data-expanded', 'true')
  expect(container.querySelectorAll('.assessment-question-editor')).toHaveLength(1)

  const navigator = screen.getByRole('complementary', { name: 'Question navigator' })
  expect(within(navigator).getAllByRole('button', { name: /Go to question/ })).toHaveLength(100)
  await userEvent.type(within(navigator).getByPlaceholderText('Search questions'), 'Question 100')
  expect(within(navigator).getAllByRole('button', { name: /Go to question/ })).toHaveLength(1)
  await userEvent.click(within(navigator).getByRole('button', { name: /Question 100/ }))

  expect(screen.getByRole('group', { name: 'Question 100' })).toHaveAttribute('data-expanded', 'true')
  expect(screen.getByRole('group', { name: 'Question 1' })).toHaveAttribute('data-expanded', 'true')
  expect(container.querySelectorAll('.assessment-question-editor')).toHaveLength(2)

  expect(screen.queryByRole('button', { name: 'Outline' })).not.toBeInTheDocument()
  expect(within(navigator).getByRole('combobox', { name: 'Filter by question type' })).toBeVisible()
  expect(within(navigator).getByRole('combobox', { name: 'Filter by required state' })).toBeVisible()
  expect(within(navigator).getByRole('checkbox', { name: 'Needs attention' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Collapse all questions' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Expand all questions' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Assignment preview' }))
  expect(await screen.findByRole('dialog', { name: 'Learner preview' })).toBeVisible()
}, 15_000)

it('opens the import drawer and copies selected questions from another draft', async () => {
  const sourceQuestion = { id: 'source-question', type: 'multiple-choice' as const, prompt: 'Imported morphology question', points: '1', required: true, options: ['A', 'B'], answerKey: ['A'], feedback: '' }
  api.listAssessmentDrafts.mockResolvedValue({
    total: 2,
    items: [
      { id: 'draft-1', title: 'Lung pathology', status: 'draft', revision: 1, document: { title: 'Lung pathology', items: [], settings: {} } },
      { id: 'source-draft', title: 'Source assessment', status: 'draft', revision: 3, document: { title: 'Source assessment', items: [sourceQuestion], settings: {} } },
    ],
  })
  api.importAssessmentQuestions.mockResolvedValue({
    id: 'draft-1', title: 'Lung pathology', status: 'draft', revision: 2,
    document: { title: 'Lung pathology', items: [{ ...sourceQuestion, id: 'imported-question' }], settings: {} },
  })

  render(<MemoryRouter initialEntries={['/admin/assessments/draft-1']}><Routes>
    <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
  </Routes></MemoryRouter>)

  expect(await screen.findByRole('heading', { name: 'Lung pathology' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Import questions' }))
  const importDialog = screen.getByRole('dialog', { name: 'Import assessment' })
  expect(importDialog).toBeVisible()
  await userEvent.selectOptions(within(importDialog).getByRole('combobox', { name: 'Source assessment' }), 'source-draft')
  await userEvent.click(within(importDialog).getByRole('button', { name: 'Select all shown' }))
  await userEvent.click(within(importDialog).getByRole('button', { name: 'Import selected (1)' }))

  expect(api.importAssessmentQuestions).toHaveBeenCalledWith('draft-1', 'source-draft', ['source-question'], 1)
  expect(await screen.findByRole('group', { name: 'Question 1' })).toBeVisible()
  expect(screen.queryByRole('dialog', { name: 'Import assessment' })).not.toBeInTheDocument()
})

it('saves the current sectioned assessment as a server-backed template', async () => {
  const document = {
    schema: 'pathlab.assessment/2' as const,
    title: 'Current assessment',
    presentation: {}, settings: {},
    sections: [{ id: 'section-1', title: 'Review', items: [{ id: 'question-1', type: 'short-answer' as const, prompt: 'Diagnosis?' }] }],
  }
  api.getAssessmentDraft.mockResolvedValue({ id: 'draft-1', title: document.title, status: 'draft', revision: 1, document })
  api.createAssessmentDraft.mockResolvedValue({ id: 'template-1', title: 'Template — Lung review', status: 'draft', revision: 1, document: { ...document, title: 'Template — Lung review' } })

  render(<MemoryRouter initialEntries={['/admin/assessments/draft-1']}><Routes>
    <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
  </Routes></MemoryRouter>)

  expect(await screen.findByRole('heading', { name: 'Questions' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Templates & import' }))
  await userEvent.type(screen.getByRole('textbox', { name: 'Template name' }), 'Lung review')
  await userEvent.click(screen.getByRole('button', { name: 'Save template' }))

  expect(api.createAssessmentDraft).toHaveBeenCalledWith(
    'Template — Lung review',
    expect.objectContaining({ title: 'Template — Lung review', sections: document.sections }),
    undefined,
  )
  expect(await screen.findByText('Lung review is ready to use.')).toBeVisible()
  expect(screen.getByRole('button', { name: /Lung review/ })).toBeVisible()
})

it('reorders questions by dragging the navigator and persists the new order', async () => {
  vi.useFakeTimers()
  const items = [
    { id: 'question-1', type: 'multiple-choice' as const, prompt: 'First question', points: '1', required: true, options: ['A', 'B'], answerKey: ['A'], feedback: '' },
    { id: 'question-2', type: 'multiple-choice' as const, prompt: 'Second question', points: '1', required: true, options: ['A', 'B'], answerKey: ['A'], feedback: '' },
  ]
  api.getAssessmentDraft.mockResolvedValue({
    id: 'draft-1', title: 'Reorder assessment', status: 'draft', revision: 1,
    document: { title: 'Reorder assessment', items, settings: {} },
  })

  const { container } = render(
    <MemoryRouter initialEntries={['/admin/assessments/draft-1']}>
      <Routes><Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} /></Routes>
    </MemoryRouter>,
  )
  await act(async () => { await Promise.resolve() })

  const navigator = screen.getByRole('complementary', { name: 'Question navigator' })
  expect(container.querySelector('.assessment-question-badges .assessment-required-badge')).toHaveTextContent('Required')
  fireEvent.click(screen.getByRole('button', { name: 'Collapse all questions' }))
  expect(container.querySelectorAll('[data-expanded="true"]')).toHaveLength(0)
  fireEvent.click(screen.getByRole('button', { name: 'Expand all questions' }))
  expect(container.querySelectorAll('[data-expanded="true"]')).toHaveLength(2)
  const second = within(navigator).getByRole('button', { name: /Go to question 2: Second question/ })
  const firstDragHandle = within(navigator).getByRole('button', { name: 'Drag question 1 to reorder' })
  const originalElementFromPoint = document.elementFromPoint
  Object.defineProperty(document, 'elementFromPoint', { configurable: true, value: vi.fn(() => second.closest('li')) })
  fireEvent.pointerDown(firstDragHandle, { pointerId: 1, button: 0, clientX: 10, clientY: 10 })
  expect(document.body.querySelector('.assessment-drag-preview')).toHaveTextContent('First question')
  expect(firstDragHandle.closest('li')).toHaveClass('is-dragging')
  fireEvent.pointerMove(firstDragHandle, { pointerId: 1, clientX: 10, clientY: 60 })
  expect(second.closest('li')).toHaveClass('is-drop-target')
  fireEvent.pointerUp(firstDragHandle, { pointerId: 1, button: 0, clientX: 10, clientY: 60 })
  Object.defineProperty(document, 'elementFromPoint', { configurable: true, value: originalElementFromPoint })

  expect(within(navigator).getAllByRole('button', { name: /Go to question/ }).map((button) => button.getAttribute('aria-label'))).toEqual([
    expect.stringContaining('Go to question 1: Second question'),
    expect.stringContaining('Go to question 2: First question'),
  ])
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  expect(api.saveAssessmentDraft).toHaveBeenCalledWith('draft-1', 1, expect.objectContaining({
    items: [expect.objectContaining({ id: 'question-2' }), expect.objectContaining({ id: 'question-1' })],
  }))
})

it('autosaves a local edit once without treating the server acknowledgement as another edit', async () => {
  vi.useFakeTimers()
  render(
    <StrictMode>
      <MemoryRouter initialEntries={['/admin/assessments/draft-1']}>
        <Routes>
          <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
        </Routes>
      </MemoryRouter>
    </StrictMode>,
  )

  await act(async () => { await Promise.resolve() })
  expect(api.saveAssessmentDraft).not.toHaveBeenCalled()
  expect(screen.getByText('All changes saved')).toBeVisible()
  fireEvent.click(screen.getAllByRole('button', { name: 'Add question' })[0])
  fireEvent.click(screen.getByRole('button', { name: 'Add multiple choice' }))
  expect(screen.getByText('Saving…')).toBeVisible()

  await act(async () => {
    await vi.advanceTimersByTimeAsync(750)
  })
  expect(api.saveAssessmentDraft).toHaveBeenCalledTimes(1)
  expect(screen.getByText('All changes saved')).toBeVisible()

  await act(async () => {
    await vi.advanceTimersByTimeAsync(3_000)
  })
  expect(api.saveAssessmentDraft).toHaveBeenCalledTimes(1)
})
