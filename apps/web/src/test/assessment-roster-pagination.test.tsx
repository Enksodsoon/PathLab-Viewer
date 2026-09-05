import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

import { AssessmentCourseRosterPage } from '../pages/AssessmentCourseRosterPage'

const api = vi.hoisted(() => ({
  assessmentCourseRosterExportUrl: vi.fn(() => '/export.csv'),
  commitAssessmentCourseRoster: vi.fn(),
  getAssessmentCourse: vi.fn(),
  listAllAssessmentCourseRoster: vi.fn(),
  listAssessmentCourseRoster: vi.fn(),
  previewAssessmentCourseRoster: vi.fn(),
  removeAllAssessmentCourseLearners: vi.fn(),
  updateAssessmentCourseEnrollment: vi.fn(),
  updateAssessmentCourseLearner: vi.fn(),
}))

vi.mock('../assessment/api', () => ({ ...api, AssessmentHttpError: class AssessmentHttpError extends Error {} }))
vi.mock('../assessment/rosterFiles', () => ({
  downloadRosterCsvTemplate: vi.fn(),
  downloadRosterExcel: vi.fn(),
  downloadRosterExcelTemplate: vi.fn(),
  parseRosterFile: vi.fn(),
  ROSTER_COLUMNS: [],
}))
vi.mock('../theme/ThemeControl', () => ({ ThemeControl: () => <div aria-label="Theme preference" /> }))

beforeEach(() => {
  api.getAssessmentCourse.mockResolvedValue({ name: 'Thoracic Pathology', courseCode: 'PATH 301' })
  api.listAssessmentCourseRoster.mockResolvedValue({
    total: 14,
    columns: [
      { key: 'student_id', label: 'Student ID', sortable: true },
      { key: 'name', label: 'Name', sortable: true },
      { key: 'email', label: 'Email', sortable: true },
    ],
    items: Array.from({ length: 14 }, (_, index) => ({
      id: `learner-${index}`,
      studentId: `6600${index}`,
      firstName: `Learner ${index}`,
      lastName: '',
      displayName: `Learner ${index}`,
      group: 'Year 3',
      subgroup: 'Lab A',
      email: `learner${index}@example.edu`,
      metadata: {},
      status: 'active',
    })),
  })
})

it('changes the number of students per page without mapping vertical wheel movement to the wide roster', async () => {
  render(<MemoryRouter initialEntries={['/admin/assessments/courses/course-1/roster']}><Routes><Route path="/admin/assessments/courses/:courseId/roster" element={<AssessmentCourseRosterPage />} /></Routes></MemoryRouter>)

  const pageSize = await screen.findByRole('combobox', { name: 'Students per page' })
  expect(pageSize).toHaveValue('25')
  fireEvent.change(pageSize, { target: { value: '10' } })

  await waitFor(() => expect(api.listAssessmentCourseRoster).toHaveBeenLastCalledWith('course-1', expect.objectContaining({ limit: 10, offset: 0 })))

  const scroller = screen.getByLabelText('Scrollable course roster')
  Object.defineProperties(scroller, {
    clientWidth: { configurable: true, value: 500 },
    scrollWidth: { configurable: true, value: 900 },
    scrollLeft: { configurable: true, writable: true, value: 0 },
  })
  fireEvent.wheel(scroller, { deltaX: 0, deltaY: 80 })
  expect(scroller.scrollLeft).toBe(0)
  expect(screen.getByLabelText('Page history')).toContainElement(screen.getByRole('button', { name: 'Back' }))
  expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeVisible()
})
