import { Archive, ArrowCounterClockwise, CaretDown, CaretUp, CaretUpDown, ChartBar, Check, Copy, Eye, MagnifyingGlass, PencilSimple, Plus, X } from '@phosphor-icons/react'
import { useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  archiveAssessmentDraft,
  createAssessmentDraft,
  duplicateAssessmentDraft,
  getAssessmentCourse,
  listAssessmentAdministrations,
  listAssessmentCourses,
  listAssessmentDrafts,
  previewAssessmentDraft,
  restoreAssessmentDraft,
  saveAssessmentDraft,
  setAssessmentAdministrationStatus,
  type AssessmentAdministrationSummary,
  type AssessmentCourse,
} from '../assessment/api'
import { AssessmentToolbar, AssessmentWorkspaceNav } from '../components/assessment/AssessmentChrome'
import type { AssessmentDraft, AssessmentItem } from '../assessment/types'
import './assessment.css'

const emptyDocument = {
  title: 'Untitled assessment',
  items: [],
  settings: { mode: 'formative' as const, shuffleQuestions: false },
}

type AssessmentSortKey = 'title' | 'course' | 'class' | 'status' | 'progress' | 'modified'
type AssessmentSortDirection = 'asc' | 'desc'

export function InlineAssessmentTitle({ draft, version, showDirectory = true, disabled = false, onOpen, onSaved, onError }: {
  draft: AssessmentDraft
  version: number
  showDirectory?: boolean
  disabled?: boolean
  onOpen: () => void
  onSaved: (saved: AssessmentDraft) => void
  onError: (message: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(draft.title)
  const [busy, setBusy] = useState(false)

  useEffect(() => setValue(draft.title), [draft.title])

  function cancel() {
    setValue(draft.title)
    setEditing(false)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const title = value.trim()
    if (!title || title === draft.title) {
      cancel()
      return
    }
    setBusy(true)
    try {
      const saved = await saveAssessmentDraft(draft.id, draft.revision, { ...draft.document, title })
      onSaved(saved)
      setEditing(false)
    } catch {
      setValue(draft.title)
      onError('Rename failed because the draft changed. Refresh and try again.')
    } finally {
      setBusy(false)
    }
  }

  if (editing) {
    return <form className="assessment-inline-rename" onSubmit={(event) => void submit(event)}>
      <input
        autoFocus
        aria-label={`Rename ${draft.title}`}
        maxLength={200}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event: KeyboardEvent<HTMLInputElement>) => { if (event.key === 'Escape') cancel() }}
      />
      <button type="submit" aria-label="Save assessment name" title="Save name" disabled={busy || !value.trim()}><Check aria-hidden="true" /></button>
      <button type="button" aria-label="Cancel rename" title="Cancel rename" onClick={cancel}><X aria-hidden="true" /></button>
    </form>
  }

  return <div className="assessment-title-cell">
    <button className="assessment-title-button" type="button" onClick={onOpen} disabled={disabled}>
      <strong>{draft.title}</strong>
      {showDirectory && (draft.courseName || draft.className) ? <span className="assessment-draft-directory">{draft.courseName ?? 'Course'}{draft.className ? <> <span aria-hidden="true">›</span> {draft.className}</> : null}</span> : null}
      <small>{draft.document.items.length} questions · version {version}</small>
    </button>
    <button className="assessment-rename-button" type="button" aria-label={`Rename ${draft.title}`} title={disabled ? 'Restore this assessment before renaming it' : 'Rename assessment'} disabled={disabled} onClick={() => setEditing(true)}><PencilSimple aria-hidden="true" /></button>
  </div>
}

export function LearnerPreviewItem({ item, index }: { item: AssessmentItem; index: number }) {
  const typeLabel = item.type.replaceAll('-', ' ')
  const choiceType = item.type === 'checkboxes' ? 'checkbox' : 'radio'
  const [diagnosticMarked, setDiagnosticMarked] = useState(false)

  return <section className="assessment-preview-question">
    <div className="assessment-preview-meta">
      <span>Question {index + 1}</span>
      <span>{typeLabel}{item.points ? ` · ${item.points} pts` : ''}</span>
    </div>
    <h3>{item.prompt || 'Untitled question'}{item.required ? <span aria-label="Required"> *</span> : null}</h3>
    {item.options?.length ? <div className="assessment-preview-options">
      {item.options.map((option) => <label key={option.id}>
        <input name={`preview-${item.id}`} type={choiceType} />
        <span>{option.label || 'Untitled option'}</span>
      </label>)}
    </div> : null}
    {item.type === 'short-answer' ? <input className="assessment-preview-text" aria-label="Short answer preview" placeholder="Type a short answer" /> : null}
    {item.type === 'paragraph' ? <textarea className="assessment-preview-text" aria-label="Paragraph answer preview" placeholder="Type a long answer" rows={4} /> : null}
    {item.type === 'diagnostic-field' ? <button
      className="assessment-preview-diagnostic"
      type="button"
      aria-pressed={diagnosticMarked}
      onClick={() => setDiagnosticMarked((marked) => !marked)}
    >
      <Eye aria-hidden="true" />
      <div><strong>{diagnosticMarked ? 'Test marker placed' : 'Try the slide selection'}</strong><small>{diagnosticMarked ? 'Click again to clear this temporary marker.' : 'Click to rehearse placing a diagnostic selection.'}</small></div>
      {diagnosticMarked ? <span className="assessment-preview-marker" aria-hidden="true" /> : null}
    </button> : null}
    {item.type === 'information' ? <p className="assessment-preview-information">Information block — no response is required.</p> : null}
  </section>
}

export function AssessmentAdminPage() {
  const navigate = useNavigate()
  const [drafts, setDrafts] = useState<AssessmentDraft[]>([])
  const [administrations, setAdministrations] = useState<AssessmentAdministrationSummary[]>([])
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sortKey, setSortKey] = useState<AssessmentSortKey>('modified')
  const [sortDirection, setSortDirection] = useState<AssessmentSortDirection>('desc')
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [busyAdministrationId, setBusyAdministrationId] = useState<string | null>(null)
  const [preview, setPreview] = useState<AssessmentDraft['document'] | null>(null)
  const [previewResetKey, setPreviewResetKey] = useState(0)
  const [courses, setCourses] = useState<AssessmentCourse[]>([])
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createCourseId, setCreateCourseId] = useState('')
  const [createClassId, setCreateClassId] = useState('')
  const [createCourse, setCreateCourse] = useState<AssessmentCourse | null>(null)
  const [createBusy, setCreateBusy] = useState(false)

  useEffect(() => {
    void Promise.all([listAssessmentDrafts(), listAssessmentAdministrations(), listAssessmentCourses()])
      .then(([draftResult, administrationResult, courseResult]) => {
        setDrafts(draftResult.items)
        setAdministrations(administrationResult.items)
        setCourses(courseResult.items)
        setState('ready')
      })
      .catch(() => setState('error'))
  }, [])

  useEffect(() => {
    if (!preview) return
    const previousOverflow = document.body.style.overflow
    const closeOnEscape = (event: globalThis.KeyboardEvent) => { if (event.key === 'Escape') setPreview(null) }
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [preview])

  async function chooseCreateCourse(courseId: string) {
    setCreateCourseId(courseId)
    setCreateClassId('')
    setCreateCourse(null)
    if (!courseId) return
    try {
      setCreateCourse(await getAssessmentCourse(courseId))
    } catch {
      setMessage('Classes for that course could not be loaded.')
    }
  }

  async function createNew() {
    setCreateBusy(true)
    setMessage('')
    try {
      const context = createCourseId ? { courseId: createCourseId, ...(createClassId ? { classId: createClassId } : {}) } : undefined
      const draft = await createAssessmentDraft(emptyDocument.title, emptyDocument, context)
      const search = createCourseId
        ? `?courseId=${encodeURIComponent(createCourseId)}${createClassId ? `&classId=${encodeURIComponent(createClassId)}` : ''}`
        : ''
      navigate(`/admin/assessments/${draft.id}${search}`)
    } catch {
      setMessage('A new assessment could not be created.')
      setCreateBusy(false)
    }
  }

  async function duplicate(id: string) {
    const created = await duplicateAssessmentDraft(id)
    setDrafts((current) => [created, ...current])
  }

  async function archive(id: string) {
    const updated = await archiveAssessmentDraft(id)
    setDrafts((current) => current.map((item) => item.id === id ? updated : item))
    setStatusFilter('archived')
    setMessage(`${updated.title} moved to Archived. Restore it to make changes.`)
  }

  async function restore(id: string) {
    const updated = await restoreAssessmentDraft(id)
    setDrafts((current) => current.map((item) => item.id === id ? updated : item))
    setStatusFilter('all')
    setMessage(`${updated.title} restored to Draft.`)
  }

  function renamed(previousTitle: string, saved: AssessmentDraft) {
    setDrafts((current) => current.map((item) => item.id === saved.id ? saved : item))
    setAdministrations((current) => current.map((item) => item.draftId === saved.id ? { ...item, title: saved.title } : item))
    setMessage(`${previousTitle} renamed to ${saved.title}.`)
  }

  async function showPreview(draft: AssessmentDraft) {
    setMessage('')
    try {
      const result = await previewAssessmentDraft(draft.id)
      setPreview(result.learnerManifest)
    } catch {
      setMessage('Preview is unavailable until required question details are complete.')
    }
  }

  async function changeStatus(administration: AssessmentAdministrationSummary, targetStatus: 'draft' | 'open' | 'closed') {
    if (targetStatus === administration.status) return
    setMessage('')
    setBusyAdministrationId(administration.id)
    try {
      const updated = await setAssessmentAdministrationStatus(administration.id, administration.status, targetStatus)
      setAdministrations((current) => current.map((item) => item.id === administration.id ? { ...item, status: updated.status } : item))
      setMessage(`Assessment status changed to ${updated.status}.`)
    } catch {
      setMessage('That status transition is not available. Close another live activity or prepare its slide assets first.')
    } finally {
      setBusyAdministrationId(null)
    }
  }

  const latestAdministrationByDraft = useMemo(() => {
    const latest = new Map<string, AssessmentAdministrationSummary>()
    administrations.forEach((administration) => {
      if (!latest.has(administration.draftId)) latest.set(administration.draftId, administration)
    })
    return latest
  }, [administrations])

  function dashboardStatus(draft: AssessmentDraft): 'draft' | 'open' | 'closed' | 'archived' {
    if (draft.status === 'archived') return 'archived'
    const status = latestAdministrationByDraft.get(draft.id)?.status
    return status === 'open' || status === 'closed' ? status : 'draft'
  }

  const visibleDrafts = drafts.filter((draft) => {
    const status = dashboardStatus(draft)
    return draft.title.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
      && (statusFilter === 'all' || status === statusFilter)
  }).sort((left, right) => {
    const leftAdministration = latestAdministrationByDraft.get(left.id)
    const rightAdministration = latestAdministrationByDraft.get(right.id)
    const statusOrder = { draft: 0, open: 1, closed: 2, archived: 3 }
    const progress = (administration?: AssessmentAdministrationSummary) => administration?.expectedParticipants
      ? administration.completedParticipants / administration.expectedParticipants
      : administration?.responses ?? 0
    let comparison = 0
    if (sortKey === 'title') comparison = left.title.localeCompare(right.title, undefined, { sensitivity: 'base' })
    if (sortKey === 'course') comparison = (left.courseName ?? '').localeCompare(right.courseName ?? '', undefined, { sensitivity: 'base' })
    if (sortKey === 'class') comparison = (left.className ?? '').localeCompare(right.className ?? '', undefined, { sensitivity: 'base' })
    if (sortKey === 'status') comparison = statusOrder[dashboardStatus(left)] - statusOrder[dashboardStatus(right)]
    if (sortKey === 'progress') comparison = progress(leftAdministration) - progress(rightAdministration)
    if (sortKey === 'modified') comparison = Date.parse(leftAdministration?.createdAt ?? '') - Date.parse(rightAdministration?.createdAt ?? '')
    if (!Number.isFinite(comparison) || comparison === 0) comparison = left.title.localeCompare(right.title, undefined, { sensitivity: 'base' })
    return sortDirection === 'asc' ? comparison : -comparison
  })

  function changeSort(nextKey: AssessmentSortKey) {
    if (sortKey === nextKey) {
      setSortDirection((current) => current === 'asc' ? 'desc' : 'asc')
      return
    }
    setSortKey(nextKey)
    setSortDirection(nextKey === 'title' || nextKey === 'course' || nextKey === 'class' || nextKey === 'status' ? 'asc' : 'desc')
  }

  function sortHeading(label: string, key: AssessmentSortKey) {
    const active = sortKey === key
    const SortIcon = !active ? CaretUpDown : sortDirection === 'asc' ? CaretUp : CaretDown
    return <button
      className={`assessment-sort-heading ${active ? 'is-active' : ''}`}
      type="button"
      aria-label={`Sort by ${label}${active ? `, currently ${sortDirection === 'asc' ? 'ascending' : 'descending'}` : ''}`}
      aria-pressed={active}
      onClick={() => changeSort(key)}
    >
      <span>{label}</span><SortIcon aria-hidden="true" />
    </button>
  }

  const dashboardMetrics = [
    { label: 'Drafts', status: 'draft', color: 'var(--warning)', value: drafts.filter((item) => dashboardStatus(item) === 'draft').length },
    { label: 'Open', status: 'open', color: 'var(--success)', value: drafts.filter((item) => dashboardStatus(item) === 'open').length },
    { label: 'Closed', status: 'closed', color: 'var(--danger)', value: drafts.filter((item) => dashboardStatus(item) === 'closed').length },
    { label: 'Archived', status: 'archived', color: 'var(--muted)', value: drafts.filter((item) => dashboardStatus(item) === 'archived').length },
  ]
  const assessmentTotal = dashboardMetrics.reduce((total, metric) => total + metric.value, 0)
  let metricCursor = 0
  const metricGradient = assessmentTotal === 0
    ? 'var(--border-soft) 0 100%'
    : dashboardMetrics.flatMap((metric) => {
        if (metric.value === 0) return []
        const start = metricCursor
        metricCursor += (metric.value / assessmentTotal) * 100
        return [`${metric.color} ${start}% ${metricCursor}%`]
      }).join(', ')

  return <>
    <AssessmentToolbar title="Assessments">
      <label className="assessment-search">
        <MagnifyingGlass aria-hidden="true" />
        <span className="visually-hidden">Search assessments</span>
        <input type="search" placeholder="Search assessments" value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>
      <label className="assessment-status-filter"><span className="visually-hidden">Filter assessment status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">Status: All</option><option value="draft">Draft</option><option value="open">Open</option><option value="closed">Closed</option><option value="archived">Archived</option></select></label>
      <button className="assessment-primary assessment-icon-primary" type="button" aria-label="New assessment" title="New assessment" onClick={() => setCreateDialogOpen(true)}><Plus aria-hidden="true" /></button>
    </AssessmentToolbar>
    <div className="assessment-main">
      <header className="assessment-page-header"><div><h1>My Assessments</h1><p>Create, publish, and review pathology assessments from the same PathLab workspace.</p></div></header>
      <section className="assessment-metrics" aria-label="Assessment status">
        <div className="assessment-status-donut" role="img" aria-label={`${assessmentTotal} assessments by status`} style={{ background: `conic-gradient(${metricGradient})` }}>
          <div><strong>{assessmentTotal}</strong><span>Total</span></div>
        </div>
        <div className="assessment-status-legend">
          {dashboardMetrics.map((metric) => <button
            key={metric.label}
            className={`assessment-status-legend-item assessment-status-legend-item--${metric.status} ${statusFilter === metric.status ? 'active' : ''}`}
            type="button"
            aria-pressed={statusFilter === metric.status}
            aria-label={`Show ${metric.label.toLocaleLowerCase()} assessments`}
            onClick={() => setStatusFilter((current) => current === metric.status ? 'all' : metric.status)}
          >
            <i aria-hidden="true" />
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <small>{assessmentTotal > 0 ? `${Math.round((metric.value / assessmentTotal) * 100)}%` : '0%'}</small>
          </button>)}
        </div>
      </section>
      <AssessmentWorkspaceNav />
      {message ? <p className="assessment-dashboard-message" role="status">{message}</p> : null}
      {state === 'loading' ? <p role="status">Loading assessments…</p> : null}
      {state === 'error' ? <p role="alert">Assessment is currently unavailable.</p> : null}
      <div className="assessment-table-wrap"><table className="assessment-table assessment-admin-table"><caption className="visually-hidden">Assessments</caption>
        <colgroup>
          <col className="assessment-col-title" />
          <col className="assessment-col-course" />
          <col className="assessment-col-class" />
          <col className="assessment-col-status" />
          <col className="assessment-col-progress" />
          <col className="assessment-col-modified" />
          <col className="assessment-col-actions" />
        </colgroup>
        <thead><tr>
          <th aria-sort={sortKey === 'title' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>{sortHeading('Assessment', 'title')}</th>
          <th aria-sort={sortKey === 'course' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>{sortHeading('Course', 'course')}</th>
          <th aria-sort={sortKey === 'class' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>{sortHeading('Class', 'class')}</th>
          <th aria-sort={sortKey === 'status' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>{sortHeading('Status', 'status')}</th>
          <th aria-sort={sortKey === 'progress' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>{sortHeading('Progress', 'progress')}</th>
          <th aria-sort={sortKey === 'modified' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>{sortHeading('Modified', 'modified')}</th>
          <th>Actions</th>
        </tr></thead><tbody>{visibleDrafts.map((draft) => {
        const latest = latestAdministrationByDraft.get(draft.id)
        const status = dashboardStatus(draft)
        const modified = latest ? new Date(latest.createdAt).toLocaleDateString() : 'Unpublished'
        const expected = latest?.expectedParticipants ?? null
        const completed = latest?.completedParticipants ?? 0
        const completionPercent = expected && expected > 0 ? Math.min(100, Math.round((completed / expected) * 100)) : 0
        const archived = draft.status === 'archived'
        return <tr key={draft.id} className={archived ? 'assessment-row--archived' : undefined}>
          <td className="assessment-cell-assessment"><InlineAssessmentTitle draft={draft} version={latest?.version ?? 0} showDirectory={false} disabled={archived} onOpen={() => navigate(`/admin/assessments/${draft.id}`)} onSaved={(saved) => renamed(draft.title, saved)} onError={setMessage} /></td>
          <td className="assessment-cell-context assessment-cell-course" data-label="Course"><span title={draft.courseName ?? undefined}>{draft.courseName ?? '—'}</span></td>
          <td className="assessment-cell-context assessment-cell-class" data-label="Class"><span title={draft.className ?? undefined}>{draft.className ?? '—'}</span></td>
          <td className="assessment-cell-status" data-label="Status"><label className="assessment-status-control"><span className="visually-hidden">Status</span><select
              aria-label={`Status for ${draft.title}`}
              className={`assessment-status assessment-status--${status}`}
              value={status}
              disabled={draft.status === 'archived' || busyAdministrationId === latest?.id}
              onChange={(event) => { if (latest) void changeStatus(latest, event.target.value as 'draft' | 'open' | 'closed') }}
            >
              <option value="draft">Draft</option>
              <option value="open" disabled={!latest}>Open</option>
              <option value="closed" disabled={!latest}>Closed</option>
              {draft.status === 'archived' ? <option value="archived">Archived</option> : null}
            </select></label></td>
          <td className="assessment-cell-progress" data-label="Progress"><div className="assessment-completion-item assessment-completion-item--empty">
              <div
                className="assessment-completion-ring"
                role="img"
                aria-label={expected !== null ? `${completed} of ${expected} learners completed, ${completionPercent}%` : `${latest?.responses ?? 0} responses, 0% completion`}
              >
                <svg viewBox="0 0 44 44" aria-hidden="true">
                  <circle className="assessment-completion-track" cx="22" cy="22" r="18" />
                  <circle className="assessment-completion-value" cx="22" cy="22" r="18" pathLength="100" strokeDasharray={`${completionPercent} 100`} />
                </svg>
                <strong>{completionPercent}%</strong>
              </div>
            </div></td>
          <td className="assessment-cell-modified" data-label="Modified"><strong>{modified}</strong></td>
          <td className="assessment-cell-actions"><div className="assessment-row-actions">
            <button type="button" aria-label={`Preview ${draft.title}`} title={archived ? 'Restore this assessment before previewing it' : 'Preview assessment'} disabled={archived} onClick={() => void showPreview(draft)}><Eye aria-hidden="true" /></button>
            <button type="button" aria-label={`Duplicate ${draft.title}, revision ${draft.revision}`} title={archived ? 'Restore this assessment before duplicating it' : 'Duplicate assessment'} disabled={archived} onClick={() => void duplicate(draft.id)}><Copy aria-hidden="true" /></button>
            {archived ? <button className="assessment-restore-button" type="button" aria-label={`Restore ${draft.title}`} title="Restore assessment" onClick={() => void restore(draft.id)}><ArrowCounterClockwise aria-hidden="true" /></button> : <button type="button" aria-label={`Archive ${draft.title}, revision ${draft.revision}`} title="Archive assessment" onClick={() => void archive(draft.id)}><Archive aria-hidden="true" /></button>}
            <button type="button" aria-label={`View report for ${draft.title}`} title={archived ? 'Restore this assessment before viewing its report' : 'View assessment responses'} disabled={archived} onClick={() => navigate(`/admin/assessments/${draft.id}?tab=responses`)}><ChartBar aria-hidden="true" /></button>
          </div></td>
        </tr>
      })}</tbody></table>{state === 'ready' && visibleDrafts.length === 0 ? <div className="assessment-empty"><h2>No matching assessments</h2><p>Adjust the search or create a new assessment.</p></div> : null}</div>
    </div>
    {createDialogOpen ? <div className="assessment-dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !createBusy) setCreateDialogOpen(false) }}>
      <section className="assessment-create-dialog" role="dialog" aria-modal="true" aria-labelledby="create-assessment-heading">
        <header><div><span>New assessment</span><h2 id="create-assessment-heading">Choose where it belongs</h2><p>Course and class are optional. You can organize the assessment now or keep it independent.</p></div><button type="button" aria-label="Close create assessment" onClick={() => setCreateDialogOpen(false)} disabled={createBusy}><X aria-hidden="true" /></button></header>
        <div className="assessment-create-context-grid">
          <label><span>Course</span><select autoFocus value={createCourseId} onChange={(event) => void chooseCreateCourse(event.target.value)}><option value="">No course</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.name} · {course.courseCode}</option>)}</select></label>
          <label><span>Class</span><select value={createClassId} disabled={!createCourseId || !createCourse} onChange={(event) => setCreateClassId(event.target.value)}><option value="">No class</option>{createCourse?.classes?.map((classItem) => <option key={classItem.id} value={classItem.id}>{classItem.name}{classItem.sectionCode ? ` · ${classItem.sectionCode}` : ''}</option>)}</select></label>
        </div>
        <footer><button type="button" onClick={() => setCreateDialogOpen(false)} disabled={createBusy}>Cancel</button><button className="assessment-primary" type="button" onClick={() => void createNew()} disabled={createBusy}>{createBusy ? 'Creating…' : 'Create assessment'}</button></footer>
      </section>
    </div> : null}
    {preview ? <div className="assessment-preview-backdrop" onMouseDown={() => setPreview(null)}>
      <div className="assessment-drawer" role="dialog" aria-modal="true" aria-label="Learner preview" onMouseDown={(event) => event.stopPropagation()}>
        <header className="assessment-preview-header">
          <div className="assessment-preview-header-copy"><span>Learner preview</span><h2 id="assessment-preview-title">{preview.title}</h2><p>Try the questions · answers are temporary and cannot be submitted.</p></div>
          <div className="assessment-preview-header-actions">
            <button className="assessment-preview-reset" type="button" aria-label="Reset preview answers" title="Reset preview answers" onClick={() => setPreviewResetKey((key) => key + 1)}><ArrowCounterClockwise aria-hidden="true" /></button>
            <button className="assessment-preview-close" type="button" autoFocus aria-label="Close preview" title="Close preview" onClick={() => setPreview(null)}><X aria-hidden="true" /></button>
          </div>
        </header>
        <div className="assessment-preview-body" key={previewResetKey} aria-label="Interactive learner preview">
          {preview.items.length ? preview.items.map((item, index) => <LearnerPreviewItem key={item.id} item={item} index={index} />) : <div className="assessment-preview-empty"><Eye aria-hidden="true" /><h3>No questions to preview</h3><p>Add a question to see the learner experience.</p></div>}
        </div>
      </div>
    </div> : null}
  </>
}
