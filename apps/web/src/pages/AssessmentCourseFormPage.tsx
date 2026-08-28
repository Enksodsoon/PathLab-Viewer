import { ArrowLeft, Check } from '@phosphor-icons/react'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { createAssessmentCourse, getAssessmentCourse, type AssessmentCourseInput, updateAssessmentCourse } from '../assessment/api'
import { toApiDateTime, toLocalDateTimeInput } from '../assessment/dateTime'
import { AssessmentToolbar } from '../components/assessment/AssessmentChrome'
import { COURSE_ICON_OPTIONS, CourseIcon, getCourseIconOption } from '../components/assessment/CourseIcon'
import './assessment.css'

const empty: AssessmentCourseInput = { name: '', courseCode: '', semester: '', academicYear: '', iconKey: 'general', scoringMethod: 'percentage', description: '', opensAt: null, closesAt: null, status: 'draft' }

export function AssessmentCourseFormPage() {
  const { courseId } = useParams()
  const navigate = useNavigate()
  const [form, setForm] = useState(empty)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [iconListOpen, setIconListOpen] = useState(false)
  useEffect(() => {
    if (!courseId) return
    void getAssessmentCourse(courseId).then((course) => setForm({
      name: course.name, courseCode: course.courseCode, semester: course.semester,
      academicYear: course.academicYear ?? '', iconKey: course.iconKey, scoringMethod: course.scoringMethod,
      description: course.description ?? '', opensAt: toLocalDateTimeInput(course.opensAt), closesAt: toLocalDateTimeInput(course.closesAt), status: course.status,
    }))
  }, [courseId])
  const set = <K extends keyof AssessmentCourseInput>(key: K, value: AssessmentCourseInput[K]) => setForm((current) => ({ ...current, [key]: value }))
  const selectedIcon = getCourseIconOption(form.iconKey)

  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setMessage('')
    const input = { ...form, opensAt: toApiDateTime(form.opensAt), closesAt: toApiDateTime(form.closesAt) }
    try {
      const course = courseId ? await updateAssessmentCourse(courseId, input) : await createAssessmentCourse(input)
      navigate(`/admin/assessments/courses/${course.id}`)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Course could not be saved.') } finally { setSaving(false) }
  }

  return <><AssessmentToolbar title={courseId ? 'Edit course' : 'New course'} /><div className="assessment-main assessment-form-page">
    <Link className="assessment-back-link" to={courseId ? `/admin/assessments/courses/${courseId}` : '/admin/assessments/classes'}><ArrowLeft aria-hidden="true" /> Back to {courseId ? 'course' : 'courses'}</Link>
    <header className="assessment-page-header"><div><p className="assessment-kicker">Course record</p><h1>{courseId ? 'Edit course' : 'Create a course'}</h1><p>A course owns the master roster and shared teaching settings. Classes and lab groups are created inside it.</p></div></header>
    <form className="assessment-course-form" onSubmit={(event) => void save(event)}>
      <section><h2>Identity</h2><p>Use the identifiers learners and faculty already recognize.</p><div className="assessment-field-grid">
        <label className="assessment-field-wide"><span className="assessment-field-label">Course name <i aria-hidden="true">*</i></span><input required maxLength={160} value={form.name} onChange={(event) => set('name', event.target.value)} placeholder="Surgical Pathology" /></label>
        <label><span className="assessment-field-label">Course ID <i aria-hidden="true">*</i></span><input required maxLength={60} value={form.courseCode} onChange={(event) => set('courseCode', event.target.value)} placeholder="PATH 301" /></label>
        <label><span className="assessment-field-label">Semester <i aria-hidden="true">*</i></span><input required maxLength={80} value={form.semester} onChange={(event) => set('semester', event.target.value)} placeholder="Semester 1" /></label>
        <label><span className="assessment-field-label">Academic year <i aria-hidden="true">*</i></span><input required maxLength={20} value={form.academicYear} onChange={(event) => set('academicYear', event.target.value)} placeholder="2026–2027" /></label>
        <fieldset className="assessment-course-icon-picker" onKeyDown={(event) => { if (event.key === 'Escape') setIconListOpen(false) }}><legend>Course icon</legend><div className="assessment-course-icon-control">
          <button className="assessment-course-icon-trigger" type="button" aria-label={`Course icon: ${selectedIcon.label}`} title={selectedIcon.label} aria-expanded={iconListOpen} aria-controls="course-icon-options" onClick={() => setIconListOpen((open) => !open)}><CourseIcon iconKey={form.iconKey} aria-hidden="true" /></button>
          {iconListOpen ? <div className="assessment-course-icon-options" id="course-icon-options" role="listbox" aria-label="Choose course icon">{COURSE_ICON_OPTIONS.map((option) => <button key={option.key} type="button" role="option" aria-selected={form.iconKey === option.key} aria-label={option.label} title={option.label} onClick={() => { set('iconKey', option.key); setIconListOpen(false) }}><CourseIcon iconKey={option.key} aria-hidden="true" /><span className="visually-hidden">{option.label}</span></button>)}</div> : null}
        </div></fieldset>
      </div></section>
      <section><h2>Availability</h2><p>Optional. Leave either date blank when the course has no fixed opening or closing time.</p><div className="assessment-field-grid">
        <label><span className="assessment-field-label">Opens <small>Optional</small></span><input type="datetime-local" value={form.opensAt ?? ''} onChange={(event) => set('opensAt', event.target.value)} /></label>
        <label><span className="assessment-field-label">Closes <small>Optional</small></span><input type="datetime-local" value={form.closesAt ?? ''} onChange={(event) => set('closesAt', event.target.value)} /></label>
        <label>Status<select value={form.status} onChange={(event) => set('status', event.target.value as AssessmentCourseInput['status'])}><option value="draft">Draft</option><option value="active">Active</option><option value="archived">Archived</option></select></label>
      </div></section>
      <section className="assessment-course-description"><h2>Description</h2><label><span>Course description</span><textarea rows={6} maxLength={4000} value={form.description} onChange={(event) => set('description', event.target.value)} placeholder="Purpose, learning scope, prerequisites, coordinator notes, or other course information." /></label></section>
      {message ? <p className="assessment-form-error" role="alert">{message}</p> : null}
      <footer><Link to={courseId ? `/admin/assessments/courses/${courseId}` : '/admin/assessments/classes'}>Cancel</Link><button className="assessment-primary" type="submit" disabled={saving}><Check aria-hidden="true" /> {saving ? 'Saving…' : 'Save course'}</button></footer>
    </form>
  </div></>
}
