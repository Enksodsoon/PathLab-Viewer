import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { AssessmentClassesPage } from '../pages/AssessmentClassesPage'
import { AssessmentCourseDetailPage } from '../pages/AssessmentCourseDetailPage'
import { AssessmentCourseFormPage } from '../pages/AssessmentCourseFormPage'

const api = vi.hoisted(() => ({ createAssessmentCourse: vi.fn(), getAssessmentCourse: vi.fn(), listAssessmentCourses: vi.fn(), updateAssessmentCourse: vi.fn() }))
vi.mock('../assessment/api', () => api)
vi.mock('../theme/ThemeControl', () => ({ ThemeControl: () => <div aria-label="Theme preference" /> }))

beforeEach(() => api.listAssessmentCourses.mockResolvedValue({ total: 1, items: [{
  id: 'course-1', name: 'Surgical Pathology', courseCode: 'PATH 301', semester: 'Semester 1', academicYear: '2026-2027',
  iconKey: 'microscope',
  scoringMethod: 'percentage', description: 'Diagnostic pathology', opensAt: '2026-08-24T08:00:00Z', closesAt: '2026-12-18T17:00:00Z',
  status: 'active', rosterCount: 36, classCount: 3,
}] }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

it('organizes the classes workspace by course and shared roster', async () => {
  render(<MemoryRouter><AssessmentClassesPage /></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'Courses' })).toBeVisible()
  expect(screen.getByRole('link', { name: 'Create course' })).toHaveTextContent('')
  expect(screen.getByText('Surgical Pathology')).toBeVisible()
  expect(screen.getByText('PATH 301')).toBeVisible()
  expect(screen.getByText('36')).toBeVisible()
  expect(screen.getByRole('link', { name: /Surgical Pathology/ })).toHaveAttribute('href', '/admin/assessments/courses/course-1')
  expect(screen.queryByText('Class name')).not.toBeInTheDocument()
})

it('makes course identity required while keeping availability optional', () => {
  render(<MemoryRouter initialEntries={['/admin/assessments/courses/new']}><Routes><Route path="/admin/assessments/courses/new" element={<AssessmentCourseFormPage />} /></Routes></MemoryRouter>)
  expect(screen.getByLabelText(/Course name/)).toBeRequired()
  expect(screen.getByLabelText(/Course ID/)).toBeRequired()
  expect(screen.getByLabelText(/Academic year/)).toBeRequired()
  expect(screen.getByLabelText(/Opens/)).not.toBeRequired()
  expect(screen.getByLabelText(/Closes/)).not.toBeRequired()
  expect(screen.queryByLabelText('Scoring method')).not.toBeInTheDocument()
  expect(screen.getByLabelText('Course description')).toBeVisible()
  const iconToggle = screen.getByRole('button', { name: 'Course icon: General' })
  expect(iconToggle).toHaveAttribute('aria-expanded', 'false')
  fireEvent.click(iconToggle)
  const iconList = screen.getByRole('listbox', { name: 'Choose course icon' })
  expect(iconList).toBeVisible()
  expect(within(iconList).getAllByRole('option')).toHaveLength(26)
  for (const system of ['Integumentary system', 'Skeletal system', 'Muscular system', 'Nervous system', 'Endocrine system', 'Cardiovascular system', 'Lymphatic and immune system', 'Respiratory system', 'Digestive system', 'Urinary system', 'Reproductive system']) {
    expect(within(iconList).getByRole('option', { name: system })).toBeVisible()
  }
  fireEvent.click(screen.getByRole('option', { name: 'Microscopy' }))
  expect(screen.getByRole('button', { name: 'Course icon: Microscopy' })).toHaveAttribute('aria-expanded', 'false')
})

it('labels numeric semesters and sorts every course column from its header', async () => {
  api.listAssessmentCourses.mockResolvedValue({ total: 2, items: [
    { id: 'z', name: 'Zeta', courseCode: 'Z-2', semester: '2', academicYear: '2027', iconKey: 'general', scoringMethod: 'percentage', description: null, opensAt: '2026-09-01T00:00:00Z', closesAt: null, status: 'draft', rosterCount: 2, classCount: 1 },
    { id: 'a', name: 'Alpha', courseCode: 'A-10', semester: '10', academicYear: '2027', iconKey: 'science', scoringMethod: 'percentage', description: null, opensAt: '2026-08-01T00:00:00Z', closesAt: null, status: 'active', rosterCount: 10, classCount: 3 },
  ] })
  const { container } = render(<MemoryRouter><AssessmentClassesPage /></MemoryRouter>)
  expect(await screen.findByText('Semester 2')).toBeVisible()
  expect(screen.getAllByRole('button', { name: /Sort by/ })).toHaveLength(6)
  fireEvent.click(screen.getByRole('button', { name: 'Sort by Roster' }))
  let rows = container.querySelectorAll('.assessment-course-row')
  expect(rows[0]).toHaveTextContent('Zeta')
  fireEvent.click(screen.getByRole('button', { name: 'Sort by Roster, currently ascending' }))
  rows = container.querySelectorAll('.assessment-course-row')
  expect(rows[0]).toHaveTextContent('Alpha')
})

it('separates and sorts class parameters while summarizing explicit roster facts', async () => {
  api.getAssessmentCourse.mockResolvedValue({
    id: 'course-1', name: 'Surgical Pathology', courseCode: 'PATH 301', semester: 'Semester 1', academicYear: '2027', iconKey: 'microscope',
    scoringMethod: 'percentage', description: 'Diagnostic pathology', opensAt: null, closesAt: null, status: 'active', rosterCount: 10, classCount: 2,
    classes: [
      { id: 'class-b', name: 'Later class', sectionCode: 'B', description: null, location: 'Lab 2', folderId: null, rosterRule: { mode: 'all', filters: [] }, opensAt: '2026-09-01T08:00:00Z', closesAt: '2026-12-01T08:00:00Z', status: 'active', studentCount: 8 },
      { id: 'class-a', name: 'Earlier class', sectionCode: 'A', description: null, location: 'Lab 1', folderId: null, rosterRule: { mode: 'all', filters: [] }, opensAt: '2026-08-01T08:00:00Z', closesAt: '2026-11-01T08:00:00Z', status: 'draft', studentCount: 2 },
    ],
  })
  const { container } = render(<MemoryRouter initialEntries={['/admin/assessments/courses/course-1']}><Routes><Route path="/admin/assessments/courses/:courseId" element={<AssessmentCourseDetailPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'Classes and sections' })).toBeVisible()
  expect(screen.getAllByRole('button', { name: /Sort by/ })).toHaveLength(7)
  expect(screen.getByRole('img', { name: '10 learners enrolled in the shared course roster' })).toBeVisible()
  expect(screen.getByText('Course roster')).toBeVisible()
  expect(screen.queryByText('Shared course roster')).not.toBeInTheDocument()
  expect(screen.queryByText(/largest class/)).not.toBeInTheDocument()
  expect(screen.queryByText(/available to every class/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/coverage/i)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Sort by Roster' }))
  let rows = container.querySelectorAll('.assessment-section-row')
  expect(rows[0]).toHaveTextContent('Earlier class')
  fireEvent.click(screen.getByRole('button', { name: 'Sort by Roster, currently ascending' }))
  rows = container.querySelectorAll('.assessment-section-row')
  expect(rows[0]).toHaveTextContent('Later class')
})

it('renders and sorts 120 mixed-data classes without invalid dates or clipped source text', async () => {
  const classes = Array.from({ length: 120 }, (_, index) => ({
    id: `class-${index}`,
    name: index === 0 ? 'วิชาพยาธิวิทยาที่มีชื่อยาวมากสำหรับการทดสอบ responsive layout' : index === 1 ? 'A very long class name that should remain available to assistive technology and hover inspection' : `Class ${String(index + 1).padStart(3, '0')}`,
    sectionCode: index % 11 === 0 ? null : index === 2 ? 'SECTION-WITH-AN-EXCEPTIONALLY-LONG-CODE' : `S-${index + 1}`,
    description: null,
    location: index % 9 === 0 ? null : index === 3 ? 'A very long pathology laboratory location inside the north clinical sciences building' : `Lab ${index % 12 + 1}`,
    folderId: null,
    rosterRule: { mode: 'all', filters: [] },
    opensAt: index === 4 ? 'not-a-date' : index % 13 === 0 ? null : new Date(Date.UTC(2026, index % 12, index % 27 + 1, 8)).toISOString(),
    closesAt: index % 17 === 0 ? null : new Date(Date.UTC(2027, index % 12, index % 27 + 1, 17)).toISOString(),
    status: ['active', 'draft', 'closed', 'archived'][index % 4],
    studentCount: index === 119 ? 10000 : index * 7,
  }))
  api.getAssessmentCourse.mockResolvedValue({
    id: 'course-stress', name: 'Stress Test Course', courseCode: 'EDGE 999', semester: 'Semester 10', academicYear: '2026-2027', iconKey: 'science',
    scoringMethod: 'percentage', description: 'Mixed data stress fixture', opensAt: 'not-a-date', closesAt: null, status: 'active', rosterCount: 10000, classCount: classes.length, classes,
  })
  const { container } = render(<MemoryRouter initialEntries={['/admin/assessments/courses/course-stress']}><Routes><Route path="/admin/assessments/courses/:courseId" element={<AssessmentCourseDetailPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'Classes and sections' })).toBeVisible()
  expect(container.querySelectorAll('.assessment-section-row')).toHaveLength(120)
  expect(screen.getAllByText('Not set').length).toBeGreaterThan(1)
  expect(screen.queryByText(/invalid date/i)).not.toBeInTheDocument()
  expect(screen.getByTitle('วิชาพยาธิวิทยาที่มีชื่อยาวมากสำหรับการทดสอบ responsive layout')).toBeVisible()
  expect(screen.getByTitle('A very long pathology laboratory location inside the north clinical sciences building')).toBeVisible()
  expect(screen.getByRole('img', { name: '10000 learners enrolled in the shared course roster' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Sort by Roster' }))
  let rows = container.querySelectorAll('.assessment-section-row')
  expect(rows[0]).toHaveTextContent('วิชาพยาธิวิทยาที่มีชื่อยาวมากสำหรับการทดสอบ responsive layout')
  fireEvent.click(screen.getByRole('button', { name: 'Sort by Roster, currently ascending' }))
  rows = container.querySelectorAll('.assessment-section-row')
  expect(rows[0]).toHaveTextContent('Class 120')
  fireEvent.click(screen.getByRole('button', { name: 'Sort by Opens' }))
  rows = container.querySelectorAll('.assessment-section-row')
  expect(rows[rows.length - 1]).toHaveTextContent('Not set')
})
