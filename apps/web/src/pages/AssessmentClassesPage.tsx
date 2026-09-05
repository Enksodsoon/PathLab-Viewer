import { ArrowRight, Books, CaretDown, CaretUp, CaretUpDown, MagnifyingGlass, Plus, UsersThree } from '@phosphor-icons/react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { type AssessmentCourse, listAssessmentCourses } from '../assessment/api'
import { AssessmentToolbar, AssessmentWorkspaceNav } from '../components/assessment/AssessmentChrome'
import { CourseIcon } from '../components/assessment/CourseIcon'
import './assessment.css'

function dates(course: AssessmentCourse) {
  if (!course.opensAt && !course.closesAt) return 'Dates not set'
  const value = (date: string | null) => date ? new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(date)) : 'Open'
  return `${value(course.opensAt)} – ${value(course.closesAt)}`
}

type CourseSortKey = 'course' | 'semester' | 'dates' | 'roster' | 'classes' | 'status'
type SortDirection = 'asc' | 'desc'

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

function semesterLabel(value: string) {
  const trimmed = value.trim()
  return /^\d+$/.test(trimmed) ? `Semester ${trimmed}` : trimmed
}

function compareCourses(left: AssessmentCourse, right: AssessmentCourse, key: CourseSortKey) {
  if (key === 'course') return collator.compare(`${left.name} ${left.courseCode}`, `${right.name} ${right.courseCode}`)
  if (key === 'semester') return collator.compare(semesterLabel(left.semester), semesterLabel(right.semester))
  if (key === 'roster') return left.rosterCount - right.rosterCount
  if (key === 'classes') return left.classCount - right.classCount
  if (key === 'status') return collator.compare(left.status, right.status)
  if (!left.opensAt && !right.opensAt) return 0
  if (!left.opensAt) return 1
  if (!right.opensAt) return -1
  return new Date(left.opensAt).getTime() - new Date(right.opensAt).getTime()
}

export function AssessmentClassesPage() {
  const [courses, setCourses] = useState<AssessmentCourse[]>([])
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [sort, setSort] = useState<{ key: CourseSortKey; direction: SortDirection }>({ key: 'course', direction: 'asc' })
  useEffect(() => { void listAssessmentCourses().then((result) => setCourses(result.items)) }, [])
  const visible = useMemo(() => courses.filter((course) => {
    const matchesQuery = `${course.name} ${course.courseCode}`.toLowerCase().includes(query.trim().toLowerCase())
    return matchesQuery && (status === 'all' || course.status === status)
  }).sort((left, right) => compareCourses(left, right, sort.key) * (sort.direction === 'asc' ? 1 : -1)), [courses, query, sort, status])

  const changeSort = (key: CourseSortKey) => setSort((current) => current.key === key
    ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
    : { key, direction: 'asc' })

  const sortButton = (key: CourseSortKey, label: string) => {
    const active = sort.key === key
    const direction = active ? sort.direction : null
    const SortIcon = direction === 'asc' ? CaretUp : direction === 'desc' ? CaretDown : CaretUpDown
    return <button type="button" onClick={() => changeSort(key)} aria-label={`Sort by ${label}${active ? `, currently ${direction === 'asc' ? 'ascending' : 'descending'}` : ''}`}><span>{label}</span><SortIcon aria-hidden="true" /></button>
  }

  return <><AssessmentToolbar title="Courses" /><div className="assessment-main assessment-courses-page">
    <header className="assessment-page-header"><div><p className="assessment-kicker">Teaching organization</p><h1>Courses</h1><p>Manage shared rosters first, then organize learners into classes, sections, or lab groups.</p></div>
      <Link className="assessment-primary assessment-icon-link" to="/admin/assessments/courses/new" aria-label="Create course" title="Create course"><Plus aria-hidden="true" /></Link>
    </header>
    <AssessmentWorkspaceNav />
    <div className="assessment-course-tools">
      <label className="assessment-search"><MagnifyingGlass aria-hidden="true" /><span className="visually-hidden">Search courses</span><input value={query} placeholder="Search by course name or ID" onChange={(event) => setQuery(event.target.value)} /></label>
      <label><span className="visually-hidden">Filter by status</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">Status: All</option><option value="draft">Draft</option><option value="active">Active</option><option value="archived">Archived</option></select></label>
    </div>
    <section className="assessment-course-list" aria-label="Courses">
      <div className="assessment-course-list-head"><span>{sortButton('course', 'Course')}</span><span>{sortButton('semester', 'Semester')}</span><span>{sortButton('dates', 'Active dates')}</span><span>{sortButton('roster', 'Roster')}</span><span>{sortButton('classes', 'Classes')}</span><span>{sortButton('status', 'Status')}</span><span /></div>
      {visible.map((course) => <Link className="assessment-course-row" key={course.id} to={`/admin/assessments/courses/${course.id}`}>
        <span className="assessment-course-identity"><CourseIcon iconKey={course.iconKey} aria-hidden="true" /><span><strong>{course.name}</strong><small>{course.courseCode}</small></span></span>
        <span data-label="Semester">{semesterLabel(course.semester)}{course.academicYear ? <small>{course.academicYear}</small> : null}</span>
        <span data-label="Active dates">{dates(course)}</span>
        <span data-label="Roster"><UsersThree aria-hidden="true" /> {course.rosterCount}</span>
        <span data-label="Classes">{course.classCount}</span>
        <span data-label="Status"><i className={`assessment-state-dot assessment-state-dot--${course.status}`} />{course.status}</span>
        <ArrowRight aria-hidden="true" />
      </Link>)}
      {visible.length === 0 ? <div className="assessment-empty"><Books aria-hidden="true" /><h2>No courses found</h2><p>Create a course to establish its shared roster and class sections.</p></div> : null}
    </section>
  </div></>
}
