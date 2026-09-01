import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { AssessmentClassDetailPage } from '../pages/AssessmentClassDetailPage'
import { AssessmentClassFormPage } from '../pages/AssessmentClassFormPage'

const assessmentApi = vi.hoisted(() => ({
  archiveAssessmentDraft: vi.fn(),
  createAssessmentDraft: vi.fn(),
  duplicateAssessmentDraft: vi.fn(),
  getAssessmentResults: vi.fn(),
  createAssessmentCourseClass: vi.fn(),
  getAssessmentClassRosterSelection: vi.fn(),
  getAssessmentCourse: vi.fn(),
  listAllAssessmentCourseRoster: vi.fn(),
  listAssessmentAdministrations: vi.fn(),
  listAssessmentDrafts: vi.fn(),
  previewAssessmentDraft: vi.fn(),
  replaceAssessmentClassRoster: vi.fn(),
  restoreAssessmentDraft: vi.fn(),
  saveAssessmentDraft: vi.fn(),
  setAssessmentAdministrationStatus: vi.fn(),
  updateAssessmentClass: vi.fn(),
}))
const libraryApi = vi.hoisted(() => ({
  getFolderChildren: vi.fn(),
  getLibraryNavigation: vi.fn(),
  listSlides: vi.fn(),
}))
vi.mock('../assessment/api', () => assessmentApi)
vi.mock('../api', () => libraryApi)
vi.mock('../theme/ThemeControl', () => ({ ThemeControl: () => <div aria-label="Theme preference" /> }))

const course = {
  id: 'course-1', name: 'Thoracic Pathology', courseCode: 'PATH 301', semester: 'Semester 1', academicYear: '2027',
  iconKey: 'respiratory', scoringMethod: 'percentage', description: null, opensAt: null, closesAt: null, status: 'active',
  rosterCount: 3, classCount: 1, classes: [{
    id: 'class-1', name: 'Pathology Year 3', sectionCode: 'DEMO-A', description: null, location: 'Lab 2',
    folderId: 'folder-1', rosterRule: { mode: 'filters', filters: [{ field: 'group', values: ['Year 3'] }] },
    opensAt: '2026-08-24T08:00:00Z', closesAt: '2026-12-18T17:00:00Z', status: 'active', studentCount: 2,
  }],
}
const learners = [
  { id: '1', studentId: '6600001', displayName: 'Learner One', group: 'Year 3', subgroup: 'Lab A', metadata: { campus: 'Main' }, selected: true },
  { id: '2', studentId: '6600002', displayName: 'Learner Two', group: 'Year 3', subgroup: 'Lab B', metadata: { campus: 'Main' }, selected: true },
  { id: '3', studentId: '6600003', displayName: 'Learner Three', group: 'Year 2', subgroup: 'Lab A', metadata: { campus: 'North' }, selected: false },
]

beforeEach(() => {
  assessmentApi.getAssessmentCourse.mockResolvedValue(course)
  assessmentApi.getAssessmentClassRosterSelection.mockResolvedValue({ items: learners, rosterRule: course.classes[0].rosterRule, total: 3 })
  assessmentApi.updateAssessmentClass.mockResolvedValue(course.classes[0])
  assessmentApi.listAssessmentAdministrations.mockResolvedValue({ items: [{ id: 'admin-1', draftId: 'draft-1', cohortId: 'class-1', publicId: 'public-1', title: 'Thoracic spot test', version: 1, mode: 'formative', status: 'closed', responses: 2, expectedParticipants: 2, completedParticipants: 2, createdAt: '' }], total: 1 })
  const draft = { id: 'draft-1', title: 'Thoracic spot test', status: 'draft', revision: 1, courseId: 'course-1', courseName: 'Thoracic Pathology', classId: 'class-1', className: 'Pathology Year 3', document: { title: 'Thoracic spot test', items: [], settings: { mode: 'formative' } } }
  assessmentApi.listAssessmentDrafts.mockResolvedValue({ items: [draft], total: 1 })
  assessmentApi.previewAssessmentDraft.mockResolvedValue({ learnerManifest: draft.document, checksum: 'demo' })
  assessmentApi.duplicateAssessmentDraft.mockResolvedValue({ ...draft, id: 'draft-copy', title: 'Thoracic spot test copy' })
  assessmentApi.archiveAssessmentDraft.mockResolvedValue({ ...draft, status: 'archived' })
  assessmentApi.saveAssessmentDraft.mockResolvedValue({ ...draft, title: 'Renamed assessment', revision: 2, document: { ...draft.document, title: 'Renamed assessment' } })
  assessmentApi.setAssessmentAdministrationStatus.mockResolvedValue({ id: 'admin-1', status: 'open' })
  assessmentApi.getAssessmentResults.mockResolvedValue({ administration: { id: 'admin-1', mode: 'formative', status: 'closed' }, summary: { responses: 2, averagePoints: '8.500', completionRate: '1', needsGrading: 0, questions: {} }, individuals: { total: 2, items: [{ attemptId: 'attempt-1', displayName: 'Learner One', status: 'graded', scoreVersion: 1, points: '9.000', maximumPoints: '10.000', breakdown: {}, responses: {} }] } })
  assessmentApi.replaceAssessmentClassRoster.mockResolvedValue({ active: 2 })
  libraryApi.getLibraryNavigation.mockResolvedValue({ folders: [{ id: 'folder-1', parentId: null, name: 'Thoracic slides', description: '', sortOrder: 0, itemCount: 0, childCount: 1, hasChildren: true, trashedAt: null, updatedAt: '' }], capabilities: { classroom: true }, counts: {}, collections: [], savedViews: [], storage: {} })
  libraryApi.getFolderChildren.mockResolvedValue([{ id: 'folder-2', parentId: 'folder-1', name: 'Core set', description: '', sortOrder: 0, itemCount: 1, childCount: 0, hasChildren: false, trashedAt: null, updatedAt: '' }])
  libraryApi.listSlides.mockResolvedValue([{ id: 'slide-1', publicId: 'public-1', displayName: 'Lung biopsy', filename: 'lung.svs', sourceBytes: 1, state: 'published', errorCode: null, errorMessage: null, metadata: null, createdAt: '', folderId: 'folder-2', thumbnailUrl: '/thumb.jpg' }])
})
afterEach(() => { cleanup(); vi.clearAllMocks() })

it('uses open and close dates and applies roster rules instead of learner checkboxes', async () => {
  render(<MemoryRouter initialEntries={['/admin/assessments/courses/course-1/classes/class-1/edit']}><Routes><Route path="/admin/assessments/courses/:courseId/classes/:classId/edit" element={<AssessmentClassFormPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'Edit class' })).toBeVisible()
  expect(screen.queryByLabelText('Meeting schedule')).not.toBeInTheDocument()
  expect(screen.getByLabelText('Opens')).toBeVisible()
  expect(screen.getByLabelText('Closes')).toBeVisible()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  expect(screen.getByLabelText('Group')).toHaveValue('Year 3')
  fireEvent.change(screen.getByLabelText('Subgroup'), { target: { value: 'Lab A' } })
  expect(screen.getByText('1 learner matches these rules.')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Save class' }))
  await waitFor(() => expect(assessmentApi.replaceAssessmentClassRoster).toHaveBeenCalledWith('class-1', {
      mode: 'filters',
      filters: [{ field: 'group', values: ['Year 3'] }, { field: 'subgroup', values: ['Lab A'] }],
    }))
})

it('opens Classroom with the saved class folder and no folder selection step', async () => {
  render(<MemoryRouter initialEntries={['/admin/assessments/courses/course-1/classes/class-1']}><Routes><Route path="/admin/assessments/courses/:courseId/classes/:classId" element={<AssessmentClassDetailPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'Pathology Year 3' })).toBeVisible()
  expect(screen.getByText('Thoracic slides')).toBeVisible()
  expect(screen.getByText('1 slide')).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Selected students' })).toBeVisible()
  expect(screen.getByText('Learner One')).toBeVisible()
  expect(screen.getByText('Learner Two')).toBeVisible()
  expect(screen.getByText(/6600001/)).toBeVisible()
  fireEvent.change(screen.getByLabelText('Search selected students'), { target: { value: '6600002' } })
  expect(screen.queryByText('Learner One')).not.toBeInTheDocument()
  expect(screen.getByText('Learner Two')).toBeVisible()
  expect(screen.queryByLabelText('Meeting schedule')).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Start classroom' })).toHaveAttribute('href', '/admin/classroom?courseId=course-1&classId=class-1&folderId=folder-1')
  fireEvent.click(screen.getByRole('button', { name: 'Change folder' }))
  expect(screen.getByRole('dialog', { name: 'Choose a folder' })).toBeVisible()
  expect(screen.getByRole('option', { name: /Thoracic slides/ })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByLabelText('Search folders')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Open Thoracic slides' }))
  expect(screen.getByRole('option', { name: /Core set/ })).toBeVisible()
  expect(screen.getByRole('navigation', { name: 'Current folder' })).toHaveTextContent('Thoracic slides')
})

it('keeps a compact report snapshot and routes every report action to the canonical report page', async () => {
  const unpublished = { id: 'draft-2', title: 'Unpublished checkpoint', status: 'draft', revision: 1, courseId: 'course-1', courseName: 'Thoracic Pathology', classId: 'class-1', className: 'Pathology Year 3', document: { title: 'Unpublished checkpoint', items: [], settings: { mode: 'formative' } } }
  const published = (await assessmentApi.listAssessmentDrafts()).items[0]
  assessmentApi.listAssessmentDrafts.mockResolvedValue({ items: [unpublished, published], total: 2 })
  render(<MemoryRouter initialEntries={['/admin/assessments/courses/course-1/classes/class-1']}><Routes><Route path="/admin/assessments/courses/:courseId/classes/:classId" element={<AssessmentClassDetailPage />} /><Route path="/admin/assessments/:draftId" element={<h1>Canonical assessment responses</h1>} /></Routes></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'Assessments' })).toBeVisible()
  expect(await screen.findByText('Thoracic spot test')).toBeVisible()
  expect(assessmentApi.listAssessmentAdministrations).toHaveBeenCalledWith('class-1')
  expect(screen.queryByRole('button', { name: /Link existing/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Assessment menu' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Thoracic spot test.*0 questions.*version 1/ })).toBeVisible()
  expect(screen.queryByText('Thoracic Pathology › Pathology Year 3')).not.toBeInTheDocument()
  expect(screen.getByRole('img', { name: '0 responses, 0% completion' })).toBeVisible()
  expect(screen.queryByRole('tab', { name: 'Class report' })).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'View report for Unpublished checkpoint' })).toHaveAttribute('href', '/admin/assessments/draft-2?tab=responses&classId=class-1&courseId=course-1')
  expect(screen.getByRole('button', { name: 'Rename Thoracic spot test' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Preview Thoracic spot test' })).toBeVisible()
  expect(screen.getByRole('button', { name: /Duplicate Thoracic spot test/ })).toBeVisible()
  expect(screen.getByRole('button', { name: /Archive Thoracic spot test/ })).toBeVisible()
  expect(screen.getByRole('columnheader', { name: 'Name' })).toBeVisible()
  expect(screen.getByRole('columnheader', { name: 'Student ID' })).toBeVisible()
  fireEvent.change(screen.getByLabelText('Assessment'), { target: { value: 'draft-1' } })
  expect(await screen.findByText('8.500')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Open full report' })).toHaveAttribute('href', '/admin/assessments/draft-1?tab=responses&classId=class-1&courseId=course-1')
  fireEvent.click(screen.getByRole('link', { name: 'View report for Thoracic spot test' }))
  expect(await screen.findByRole('heading', { name: 'Canonical assessment responses' })).toBeVisible()
})
