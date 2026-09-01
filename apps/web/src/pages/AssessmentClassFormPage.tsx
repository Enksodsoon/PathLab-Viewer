import { ArrowLeft, Check, FunnelSimple, UsersThree } from '@phosphor-icons/react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  createAssessmentCourseClass,
  getAssessmentClassRosterSelection,
  getAssessmentCourse,
  listAllAssessmentCourseRoster,
  replaceAssessmentClassRoster,
  type AssessmentClassInput,
  type AssessmentClassRosterRule,
  type AssessmentCourse,
  updateAssessmentClass,
} from '../assessment/api'
import { toApiDateTime, toLocalDateTimeInput } from '../assessment/dateTime'
import { AssessmentToolbar } from '../components/assessment/AssessmentChrome'
import './assessment.css'

interface RosterLearner {
  id: string
  displayName: string | null
  group: string | null
  subgroup: string | null
  metadata: Record<string, string>
  selected?: boolean
}

interface RosterFacet { field: string; label: string; values: string[]; kind: 'core' | 'metadata' }

const EMPTY_RULE: AssessmentClassRosterRule = { mode: 'all', filters: [] }

function labelForMetadata(key: string) {
  return key.replaceAll('_', ' ').replace(/\b\w/g, (value) => value.toUpperCase())
}

export function AssessmentClassFormPage() {
  const { courseId = '', classId } = useParams()
  const navigate = useNavigate()
  const [course, setCourse] = useState<AssessmentCourse | null>(null)
  const [roster, setRoster] = useState<RosterLearner[]>([])
  const [form, setForm] = useState<AssessmentClassInput>({
    name: '', sectionCode: '', description: '', location: '', opensAt: null, closesAt: null, rosterRule: EMPTY_RULE,
  })
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => { void getAssessmentCourse(courseId).then(async (value) => {
    setCourse(value)
    const classItem = classId ? value.classes?.find((item) => item.id === classId) : null
    if (classItem) setForm({
      name: classItem.name,
      sectionCode: classItem.sectionCode ?? '',
      description: classItem.description ?? '',
      location: classItem.location ?? '',
      opensAt: toLocalDateTimeInput(classItem.opensAt),
      closesAt: toLocalDateTimeInput(classItem.closesAt),
      rosterRule: classItem.rosterRule ?? { mode: 'existing', filters: [] },
    })
    if (classId) {
      const selection = await getAssessmentClassRosterSelection(classId)
      setRoster(selection.items)
      setForm((current) => ({ ...current, rosterRule: selection.rosterRule }))
    } else {
      const learners = await listAllAssessmentCourseRoster(courseId)
      setRoster(learners.filter((item) => item.status === 'active'))
    }
  }).catch(() => setMessage('Class information could not be loaded.')) }, [courseId, classId])

  const facets = useMemo<RosterFacet[]>(() => {
    const values = (read: (learner: RosterLearner) => string | null | undefined) =>
      [...new Set(roster.map(read).filter((value): value is string => Boolean(value?.trim())).map((value) => value.trim()))].sort((a, b) => a.localeCompare(b))
    const result: RosterFacet[] = [
      { field: 'group', label: 'Group', values: values((learner) => learner.group), kind: 'core' },
      { field: 'subgroup', label: 'Subgroup', values: values((learner) => learner.subgroup), kind: 'core' },
    ]
    const metadataKeys = [...new Set(roster.flatMap((learner) => Object.keys(learner.metadata ?? {})))].sort()
    metadataKeys.forEach((key) => result.push({
      field: `metadata.${key}`,
      label: labelForMetadata(key),
      values: values((learner) => learner.metadata?.[key]),
      kind: 'metadata',
    }))
    return result.filter((facet) => facet.values.length)
  }, [roster])

  const filterValues = useMemo(() => new Map(form.rosterRule.filters.map((item) => [item.field, item.values[0] ?? ''])), [form.rosterRule.filters])
  const matchingLearners = useMemo(() => {
    if (form.rosterRule.mode === 'all') return roster
    if (form.rosterRule.mode === 'existing') return roster.filter((learner) => learner.selected)
    if (!form.rosterRule.filters.length) return []
    return roster.filter((learner) => form.rosterRule.filters.every((filter) => {
      const actual = filter.field === 'group'
        ? learner.group
        : filter.field === 'subgroup'
          ? learner.subgroup
          : learner.metadata?.[filter.field.replace(/^metadata\./, '')]
      return Boolean(actual && filter.values.some((value) => value.localeCompare(actual, undefined, { sensitivity: 'accent' }) === 0))
    }))
  }, [form.rosterRule, roster])

  const set = <K extends keyof AssessmentClassInput>(key: K, value: AssessmentClassInput[K]) => setForm((current) => ({ ...current, [key]: value }))
  const setRuleMode = (mode: AssessmentClassRosterRule['mode']) => set('rosterRule', { mode, filters: [] })
  const setFacet = (field: string, value: string) => setForm((current) => ({
    ...current,
    rosterRule: {
      mode: 'filters',
      filters: [
        ...current.rosterRule.filters.filter((item) => item.field !== field),
        ...(value ? [{ field, values: [value] }] : []),
      ],
    },
  }))

  async function save(event: FormEvent) {
    event.preventDefault()
    setMessage('')
    setSaving(true)
    const input = { ...form, opensAt: toApiDateTime(form.opensAt), closesAt: toApiDateTime(form.closesAt) }
    try {
      if (classId) {
        await updateAssessmentClass(classId, input)
        await replaceAssessmentClassRoster(classId, input.rosterRule)
        navigate(`/admin/assessments/courses/${courseId}/classes/${classId}`)
      } else {
        const created = await createAssessmentCourseClass(courseId, input)
        navigate(`/admin/assessments/courses/${courseId}/classes/${created.id}`)
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Class could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  const filtersEmpty = form.rosterRule.mode === 'filters' && !form.rosterRule.filters.length

  return <><AssessmentToolbar title={classId ? 'Edit class' : 'New class'} /><div className="assessment-main assessment-form-page">
    <Link className="assessment-back-link" to={classId ? `/admin/assessments/courses/${courseId}/classes/${classId}` : `/admin/assessments/courses/${courseId}`}><ArrowLeft aria-hidden="true" /> {classId ? 'Back to class' : course?.name || 'Course'}</Link>
    <header className="assessment-page-header"><div><h1>{classId ? 'Edit class' : 'Create a class'}</h1><p>Set the class dates and define its learners using roster information.</p></div></header>
    <form className="assessment-class-form" onSubmit={(event) => void save(event)}><div className="assessment-class-form-main"><section><h2>Class information</h2><div className="assessment-field-grid">
      <label className="assessment-field-wide">Class name<input required value={form.name} onChange={(event) => set('name', event.target.value)} placeholder="Section A" /></label>
      <label>Section code<input required value={form.sectionCode} onChange={(event) => set('sectionCode', event.target.value)} placeholder="SEC-A" /></label>
      <label>Location<input value={form.location} onChange={(event) => set('location', event.target.value)} placeholder="Pathology Lab 2" /></label>
      <label>Opens<input type="datetime-local" value={form.opensAt ?? ''} onChange={(event) => set('opensAt', event.target.value)} /></label>
      <label>Closes<input type="datetime-local" value={form.closesAt ?? ''} onChange={(event) => set('closesAt', event.target.value)} /></label>
      <label className="assessment-field-wide">Description<textarea rows={4} value={form.description} onChange={(event) => set('description', event.target.value)} /></label>
    </div></section></div><aside className="assessment-class-roster-select"><header><UsersThree aria-hidden="true" /><div><h2>Class roster</h2><p>{matchingLearners.length} of {roster.length} course learners</p></div></header>
      <label className="assessment-radio-row"><input type="radio" checked={form.rosterRule.mode === 'all'} onChange={() => setRuleMode('all')} /> Use the full course roster</label>
      <label className="assessment-radio-row"><input type="radio" checked={form.rosterRule.mode === 'filters'} onChange={() => setRuleMode('filters')} /> Select learners by roster information</label>
      {form.rosterRule.mode === 'existing' ? <div className="assessment-roster-existing"><FunnelSimple aria-hidden="true" /><span><strong>Current selection</strong><small>{matchingLearners.length} learners are kept until you choose a rule.</small></span></div> : null}
      {form.rosterRule.mode === 'filters' ? <div className="assessment-roster-filters">
        {facets.filter((facet) => facet.kind === 'core').map((facet) => <label key={facet.field}>{facet.label}<select value={filterValues.get(facet.field) ?? ''} onChange={(event) => setFacet(facet.field, event.target.value)}><option value="">Any {facet.label.toLowerCase()}</option>{facet.values.map((value) => <option key={value}>{value}</option>)}</select></label>)}
        {facets.some((facet) => facet.kind === 'metadata') ? <fieldset><legend>Additional information</legend>{facets.filter((facet) => facet.kind === 'metadata').map((facet) => <label key={facet.field}>{facet.label}<select value={filterValues.get(facet.field) ?? ''} onChange={(event) => setFacet(facet.field, event.target.value)}><option value="">Any</option>{facet.values.map((value) => <option key={value}>{value}</option>)}</select></label>)}</fieldset> : null}
        <p className={matchingLearners.length ? undefined : 'assessment-form-error'}>{filtersEmpty ? 'Choose at least one roster value.' : `${matchingLearners.length} learner${matchingLearners.length === 1 ? ' matches' : 's match'} these rules.`}</p>
      </div> : null}
      {!roster.length ? <p>No active learners are in the course roster yet.</p> : null}
    </aside><footer>{message ? <p role="alert" className="assessment-form-error">{message}</p> : <span />}<div><Link to={classId ? `/admin/assessments/courses/${courseId}/classes/${classId}` : `/admin/assessments/courses/${courseId}`}>Cancel</Link><button className="assessment-primary" type="submit" disabled={saving || filtersEmpty}><Check aria-hidden="true" /> {saving ? 'Saving…' : 'Save class'}</button></div></footer></form>
  </div></>
}
