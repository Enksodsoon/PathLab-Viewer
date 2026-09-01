import { ArrowLeft, ArrowRight, CaretDown, CaretUp, CaretUpDown, PencilSimple, Plus, UsersThree } from '@phosphor-icons/react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { type AssessmentCourse, type AssessmentCourseClass, getAssessmentCourse } from '../assessment/api'
import { AssessmentToolbar } from '../components/assessment/AssessmentChrome'
import './assessment.css'

const parseDate = (value: string | null) => {
  if (!value) return null
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : null
}
const readableDate = (value: string | null) => {
  const timestamp = parseDate(value)
  return timestamp === null ? 'Not set' : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(timestamp)
}
type ClassSortKey = 'class' | 'section' | 'opens' | 'closes' | 'location' | 'roster' | 'status'
type SortDirection = 'asc' | 'desc'

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

function compareNullableDates(left: string | null, right: string | null) {
  const leftTimestamp = parseDate(left)
  const rightTimestamp = parseDate(right)
  if (leftTimestamp === null && rightTimestamp === null) return 0
  if (leftTimestamp === null) return 1
  if (rightTimestamp === null) return -1
  return leftTimestamp - rightTimestamp
}

function compareClasses(left: AssessmentCourseClass, right: AssessmentCourseClass, key: ClassSortKey) {
  if (key === 'class') return collator.compare(left.name, right.name)
  if (key === 'section') return collator.compare(left.sectionCode ?? '', right.sectionCode ?? '')
  if (key === 'opens') return compareNullableDates(left.opensAt, right.opensAt)
  if (key === 'closes') return compareNullableDates(left.closesAt, right.closesAt)
  if (key === 'location') return collator.compare(left.location ?? '', right.location ?? '')
  if (key === 'roster') return left.studentCount - right.studentCount
  return collator.compare(left.status, right.status)
}

export function AssessmentCourseDetailPage() {
  const { courseId = '' } = useParams()
  const [course, setCourse] = useState<AssessmentCourse | null>(null)
  const [sort, setSort] = useState<{ key: ClassSortKey; direction: SortDirection }>({ key: 'class', direction: 'asc' })
  useEffect(() => { void getAssessmentCourse(courseId).then(setCourse) }, [courseId])
  const classes = useMemo(() => [...(course?.classes ?? [])].sort((left, right) => compareClasses(left, right, sort.key) * (sort.direction === 'asc' ? 1 : -1)), [course?.classes, sort])
  const changeSort = (key: ClassSortKey) => setSort((current) => current.key === key
    ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
    : { key, direction: 'asc' })
  const sortButton = (key: ClassSortKey, label: string) => {
    const active = sort.key === key
    const direction = active ? sort.direction : null
    const SortIcon = direction === 'asc' ? CaretUp : direction === 'desc' ? CaretDown : CaretUpDown
    return <button type="button" onClick={() => changeSort(key)} aria-label={`Sort by ${label}${active ? `, currently ${direction === 'asc' ? 'ascending' : 'descending'}` : ''}`}><span>{label}</span><SortIcon aria-hidden="true" /></button>
  }
  if (!course) return <><AssessmentToolbar title="Course" /><div className="assessment-main"><p>Loading course…</p></div></>
  return <><AssessmentToolbar title={course.courseCode} /><div className="assessment-main assessment-course-detail">
    <Link className="assessment-back-link" to="/admin/assessments/classes"><ArrowLeft aria-hidden="true" /> All courses</Link>
    <header className="assessment-course-detail-header"><div><p className="assessment-kicker">{course.courseCode} · {course.semester}</p><h1>{course.name}</h1><p>{course.description || 'No course description has been added.'}</p></div><span className={`assessment-status assessment-status--${course.status}`}>{course.status}</span></header>
    <div className="assessment-detail-actions"><Link to={`/admin/assessments/courses/${course.id}/edit`}><PencilSimple aria-hidden="true" /> Edit course</Link><Link to={`/admin/assessments/courses/${course.id}/roster`}><UsersThree aria-hidden="true" /> Manage roster</Link><Link className="assessment-primary" to={`/admin/assessments/courses/${course.id}/classes/new`}><Plus aria-hidden="true" /> New class</Link></div>
    <section className="assessment-course-overview" aria-labelledby="course-information"><div><h2 id="course-information">Course information</h2><dl><div><dt>Course ID</dt><dd>{course.courseCode}</dd></div><div><dt>Semester</dt><dd>{course.semester}</dd></div><div><dt>Academic year</dt><dd>{course.academicYear || 'Not set'}</dd></div><div><dt>Opens</dt><dd>{readableDate(course.opensAt)}</dd></div><div><dt>Closes</dt><dd>{readableDate(course.closesAt)}</dd></div></dl></div>
      <Link className="assessment-roster-summary" to={`/admin/assessments/courses/${course.id}/roster`}>
        <span className="assessment-roster-visual" role="img" aria-label={`${course.rosterCount} learners enrolled in the shared course roster`}><UsersThree aria-hidden="true" /><span><strong>{course.rosterCount}</strong><small>learners enrolled</small></span></span>
        <strong className="assessment-roster-summary-title">Course roster</strong>
      </Link>
    </section>
    <section className="assessment-section-list" aria-labelledby="class-sections"><header><div><h2 id="class-sections">Classes and sections</h2><p>Each class uses all or a selected portion of the shared course roster.</p></div><strong>{course.classCount} total</strong></header>
      <div className="assessment-section-table">
        <div className="assessment-section-list-head"><span>{sortButton('class', 'Class')}</span><span>{sortButton('section', 'Section')}</span><span>{sortButton('opens', 'Opens')}</span><span>{sortButton('closes', 'Closes')}</span><span>{sortButton('location', 'Location')}</span><span>{sortButton('roster', 'Roster')}</span><span>{sortButton('status', 'Status')}</span><span /></div>
        {classes.map((item) => <Link key={item.id} className="assessment-section-row" to={`/admin/assessments/courses/${course.id}/classes/${item.id}`}>
          <span data-label="Class" title={item.name}><strong>{item.name}</strong></span>
          <span data-label="Section" title={item.sectionCode || undefined}>{item.sectionCode || '—'}</span>
          <span data-label="Opens" title={readableDate(item.opensAt)}>{readableDate(item.opensAt)}</span>
          <span data-label="Closes" title={readableDate(item.closesAt)}>{readableDate(item.closesAt)}</span>
          <span data-label="Location" title={item.location || undefined}>{item.location || '—'}</span>
          <span data-label="Roster"><span className="assessment-section-cell-value"><UsersThree aria-hidden="true" />{item.studentCount} of {course.rosterCount}</span></span>
          <span data-label="Status"><span className="assessment-section-cell-value"><i className={`assessment-state-dot assessment-state-dot--${item.status}`} />{item.status}</span></span><ArrowRight aria-hidden="true" />
        </Link>)}
      </div>
      {!course.classes?.length ? <div className="assessment-empty"><UsersThree aria-hidden="true" /><h3>No classes yet</h3><p>Create the first class and choose whether it uses the full course roster or a subset.</p><Link className="assessment-primary" to={`/admin/assessments/courses/${course.id}/classes/new`}><Plus /> New class</Link></div> : null}
    </section>
  </div></>
}
