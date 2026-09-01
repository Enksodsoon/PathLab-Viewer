import { Archive, ArrowCounterClockwise, ArrowLeft, ArrowSquareOut, CalendarBlank, CaretRight, ChalkboardTeacher, ChartBar, Check, ClipboardText, Copy, Eye, FolderOpen, House, MagnifyingGlass, MapPin, PencilSimple, Plus, UsersThree, X } from '@phosphor-icons/react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { listSlides } from '../api'
import { classFolderOptions, loadAllLibraryFolders } from '../assessment/classFolders'
import { archiveAssessmentDraft, createAssessmentDraft, duplicateAssessmentDraft, getAssessmentClassRosterSelection, getAssessmentCourse, getAssessmentResults, listAssessmentAdministrations, listAssessmentDrafts, previewAssessmentDraft, restoreAssessmentDraft, setAssessmentAdministrationStatus, type AssessmentAdministrationSummary, type AssessmentCourse, type AssessmentResults, updateAssessmentClass } from '../assessment/api'
import { AssessmentToolbar } from '../components/assessment/AssessmentChrome'
import { assessmentItems, type AssessmentDraft } from '../assessment/types'
import type { AdminSlide, LibraryFolder } from '../types'
import { InlineAssessmentTitle, LearnerPreviewItem } from './AssessmentAdminPage'
import './assessment.css'

const readableDate = (value: string | null) => value
  ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  : 'Not set'

const ruleLabel = (field: string) => field === 'group'
  ? 'Group'
  : field === 'subgroup'
    ? 'Subgroup'
    : field.replace(/^metadata\./, '').replaceAll('_', ' ').replace(/\b\w/g, (value) => value.toUpperCase())

const slideThumbnail = (slide: AdminSlide) => slide.thumbnailUrl
  ?? (slide.state === 'ready_private' || slide.state === 'published'
    ? `/api/v1/admin/slides/${encodeURIComponent(slide.id)}/preview/thumbnail.jpg`
    : null)

const newAssessmentDocument = {
  title: 'Untitled assessment',
  items: [],
  settings: { mode: 'formative' as const },
}

export function AssessmentClassDetailPage() {
  const { courseId = '', classId = '' } = useParams()
  const responsesUrl = (draftId: string) => `/admin/assessments/${encodeURIComponent(draftId)}?${new URLSearchParams({ tab: 'responses', classId, courseId }).toString()}`
  const navigate = useNavigate()
  const [course, setCourse] = useState<AssessmentCourse | null>(null)
  const [folders, setFolders] = useState<LibraryFolder[]>([])
  const [slides, setSlides] = useState<AdminSlide[]>([])
  const [savedFolderId, setSavedFolderId] = useState<string | null>(null)
  const [draftFolderId, setDraftFolderId] = useState('')
  const [changingFolder, setChangingFolder] = useState(false)
  const [classroomEnabled, setClassroomEnabled] = useState(false)
  const [rosterCount, setRosterCount] = useState(0)
  const [selectedLearners, setSelectedLearners] = useState<Array<{ id: string; studentId: string | null; displayName: string | null; group: string | null; subgroup: string | null }>>([])
  const [learnerQuery, setLearnerQuery] = useState('')
  const [folderQuery, setFolderQuery] = useState('')
  const [folderBrowserParentId, setFolderBrowserParentId] = useState<string | null>(null)
  const [folderResultPage, setFolderResultPage] = useState(0)
  const [message, setMessage] = useState('')
  const [savingFolder, setSavingFolder] = useState(false)
  const [administrations, setAdministrations] = useState<AssessmentAdministrationSummary[]>([])
  const [drafts, setDrafts] = useState<AssessmentDraft[]>([])
  const [busyAdministrationId, setBusyAdministrationId] = useState<string | null>(null)
  const [preview, setPreview] = useState<AssessmentDraft['document'] | null>(null)
  const [previewResetKey, setPreviewResetKey] = useState(0)
  const [selectedReportDraftId, setSelectedReportDraftId] = useState('')
  const [report, setReport] = useState<AssessmentResults | null>(null)
  const [reportState, setReportState] = useState<'idle' | 'loading' | 'error'>('idle')

  useEffect(() => {
    void Promise.all([getAssessmentCourse(courseId), getAssessmentClassRosterSelection(classId), listSlides(), loadAllLibraryFolders()])
      .then(([nextCourse, selection, nextSlides, library]) => {
        const item = nextCourse.classes?.find((entry) => entry.id === classId)
        setCourse(nextCourse)
        setSavedFolderId(item?.folderId ?? null)
        setDraftFolderId(item?.folderId ?? '')
        const matchedLearners = selection.items.filter((learner) => learner.selected)
        setRosterCount(matchedLearners.length)
        setSelectedLearners(matchedLearners)
        setSlides(nextSlides)
        setFolders(library.folders)
        setClassroomEnabled(Boolean(library.navigation.capabilities?.classroom))
      })
      .catch(() => setMessage('This class could not be loaded.'))
  }, [classId, courseId])

  useEffect(() => {
    void Promise.all([listAssessmentDrafts(classId), listAssessmentAdministrations(classId)])
      .then(([draftResult, administrationResult]) => {
        setDrafts(draftResult.items)
        setAdministrations(administrationResult.items)
        setSelectedReportDraftId((current) => current || draftResult.items[0]?.id || '')
      })
      .catch(() => setMessage('Class assessments could not be loaded.'))
  }, [classId])

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

  useEffect(() => {
    if (!selectedReportDraftId) {
      setReport(null)
      setReportState('idle')
      return
    }
    const selectedAdministration = administrations.find((item) => item.draftId === selectedReportDraftId)
    if (!selectedAdministration) {
      setReport(null)
      setReportState('idle')
      return
    }
    setReportState('loading')
    void getAssessmentResults(selectedAdministration.id)
      .then((value) => { setReport(value); setReportState('idle') })
      .catch(() => { setReport(null); setReportState('error') })
  }, [administrations, selectedReportDraftId])

  const classItem = course?.classes?.find((item) => item.id === classId)
  const folderOptions = useMemo(() => classFolderOptions(folders, slides), [folders, slides])
  const savedFolder = folderOptions.find((option) => option.folder.id === savedFolderId)
  const filteredLearners = useMemo(() => {
    const query = learnerQuery.trim().toLocaleLowerCase()
    if (!query) return selectedLearners
    return selectedLearners.filter((learner) => [learner.studentId, learner.displayName, learner.group, learner.subgroup]
      .some((value) => value?.toLocaleLowerCase().includes(query)))
  }, [learnerQuery, selectedLearners])
  const folderById = useMemo(() => new Map(folders.map((folder) => [folder.id, folder])), [folders])
  const folderPath = useMemo(() => {
    const path: LibraryFolder[] = []
    const visited = new Set<string>()
    let current = folderBrowserParentId ? folderById.get(folderBrowserParentId) : undefined
    while (current && !visited.has(current.id)) {
      visited.add(current.id)
      path.unshift(current)
      current = current.parentId ? folderById.get(current.parentId) : undefined
    }
    return path
  }, [folderBrowserParentId, folderById])
  const folderPathLabels = useMemo(() => new Map(folders.map((folder) => {
    const names = [folder.name]
    const visited = new Set([folder.id])
    let parent = folder.parentId ? folderById.get(folder.parentId) : undefined
    while (parent && !visited.has(parent.id)) {
      visited.add(parent.id)
      names.unshift(parent.name)
      parent = parent.parentId ? folderById.get(parent.parentId) : undefined
    }
    return [folder.id, names.join(' / ')]
  })), [folderById, folders])
  const visibleFolderOptions = useMemo(() => {
    const query = folderQuery.trim().toLocaleLowerCase()
    return folderOptions.filter((option) => query
      ? option.folder.name.toLocaleLowerCase().includes(query)
      : option.folder.parentId === folderBrowserParentId)
  }, [folderBrowserParentId, folderOptions, folderQuery])
  const folderResultPageSize = 32
  const folderResultStart = folderResultPage * folderResultPageSize
  const displayedFolderOptions = visibleFolderOptions.slice(folderResultStart, folderResultStart + folderResultPageSize)

  useEffect(() => setFolderResultPage(0), [folderBrowserParentId, folderQuery])

  function openFolderBrowser() {
    setFolderQuery('')
    setFolderBrowserParentId(null)
    setChangingFolder(true)
  }

  function closeFolderBrowser() {
    setDraftFolderId(savedFolderId ?? '')
    setFolderQuery('')
    setFolderBrowserParentId(null)
    setChangingFolder(false)
  }

  async function saveFolder() {
    setSavingFolder(true)
    setMessage('')
    try {
      await updateAssessmentClass(classId, { folderId: draftFolderId || null })
      setSavedFolderId(draftFolderId || null)
      setChangingFolder(false)
      setMessage('Slide set saved.')
    } catch {
      setMessage('The slide set could not be saved.')
    } finally {
      setSavingFolder(false)
    }
  }

  async function createAssessment() {
    setMessage('')
    try {
      const draft = await createAssessmentDraft(newAssessmentDocument.title, newAssessmentDocument, { courseId, classId })
      navigate(`/admin/assessments/${draft.id}?classId=${encodeURIComponent(classId)}&courseId=${encodeURIComponent(courseId)}`)
    } catch {
      setMessage('A new assessment could not be created.')
    }
  }

  async function duplicateAssessment(draft: AssessmentDraft) {
    try {
      const created = await duplicateAssessmentDraft(draft.id)
      setDrafts((current) => [created, ...current])
      setMessage(`${draft.title} duplicated.`)
    } catch {
      setMessage('The assessment could not be duplicated.')
    }
  }

  async function archiveAssessment(draft: AssessmentDraft) {
    try {
      const updated = await archiveAssessmentDraft(draft.id)
      setDrafts((current) => current.map((item) => item.id === updated.id ? updated : item))
      setMessage(`${draft.title} archived.`)
    } catch {
      setMessage('The assessment could not be archived.')
    }
  }

  async function restoreAssessment(draft: AssessmentDraft) {
    try {
      const updated = await restoreAssessmentDraft(draft.id)
      setDrafts((current) => current.map((item) => item.id === updated.id ? updated : item))
      setMessage(`${draft.title} restored to Draft.`)
    } catch {
      setMessage('The assessment could not be restored.')
    }
  }

  function renamedAssessment(previousTitle: string, saved: AssessmentDraft) {
    setDrafts((current) => current.map((item) => item.id === saved.id ? saved : item))
    setAdministrations((current) => current.map((item) => item.draftId === saved.id ? { ...item, title: saved.title } : item))
    setMessage(`${previousTitle} renamed to ${saved.title}.`)
  }

  async function showAssessmentPreview(draft: AssessmentDraft) {
    try {
      const result = await previewAssessmentDraft(draft.id)
      setPreview(result.learnerManifest)
    } catch {
      setMessage('Preview is unavailable until required question details are complete.')
    }
  }

  async function changeAssessmentStatus(administration: AssessmentAdministrationSummary, target: 'draft' | 'open' | 'closed') {
    if (target === administration.status) return
    setBusyAdministrationId(administration.id)
    try {
      const updated = await setAssessmentAdministrationStatus(administration.id, administration.status, target)
      setAdministrations((current) => current.map((item) => item.id === administration.id ? { ...item, status: updated.status } : item))
      setMessage(`Assessment status changed to ${updated.status}.`)
    } catch {
      setMessage('That status transition is not available.')
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

  if (!course || !classItem) return <><AssessmentToolbar title="Class" /><div className="assessment-main"><p>{message || 'Loading class…'}</p></div></>

  const rule = classItem.rosterRule ?? { mode: 'existing' as const, filters: [] }
  const classroomUrl = savedFolderId
    ? `/admin/classroom?courseId=${encodeURIComponent(courseId)}&classId=${encodeURIComponent(classId)}&folderId=${encodeURIComponent(savedFolderId)}`
    : ''
  const selectedReportDraft = drafts.find((item) => item.id === selectedReportDraftId)
  const selectedAdministration = selectedReportDraftId ? latestAdministrationByDraft.get(selectedReportDraftId) : undefined

  return <><AssessmentToolbar title={classItem.sectionCode || classItem.name} /><div className="assessment-main assessment-class-detail">
    <Link className="assessment-back-link" to={`/admin/assessments/courses/${courseId}`}><ArrowLeft aria-hidden="true" /> {course.name}</Link>
    <header className="assessment-class-detail-header"><div><h1>{classItem.name}</h1><p>Everything needed to run this class—learners, slides, and dates.</p></div><Link to={`/admin/assessments/courses/${courseId}/classes/${classId}/edit`}><PencilSimple aria-hidden="true" /> Edit class</Link></header>
    <section className="assessment-class-dates" aria-label="Class dates">
      <div><CalendarBlank aria-hidden="true" /><span><small>Opens</small><strong>{readableDate(classItem.opensAt)}</strong></span></div>
      <div><CalendarBlank aria-hidden="true" /><span><small>Closes</small><strong>{readableDate(classItem.closesAt)}</strong></span></div>
      {classItem.location ? <div><MapPin aria-hidden="true" /><span><small>Location</small><strong>{classItem.location}</strong></span></div> : null}
    </section>
    <div className="assessment-class-hub-grid">
      <section className="assessment-class-roster-card"><header><UsersThree aria-hidden="true" /><div><h2>Class roster</h2><p>Learners are selected by rules.</p></div></header>
        <dl>
          {rule.mode === 'all' ? <div><dt>Rule</dt><dd>Full course roster</dd></div> : null}
          {rule.mode === 'existing' ? <div><dt>Rule</dt><dd>Current class selection</dd></div> : null}
          {rule.filters.map((filter) => <div key={filter.field}><dt>{ruleLabel(filter.field)}</dt><dd>{filter.values.join(', ')}</dd></div>)}
        </dl>
        <div className="assessment-class-roster-match"><small>Learner match</small><strong>{rosterCount} of {course.rosterCount} learners</strong><p>Only matching learners are included in this class.</p></div>
        <section className="assessment-class-learner-window" aria-labelledby="matched-learners-heading">
          <header><h3 id="matched-learners-heading">Selected students</h3><span>{rosterCount}</span></header>
          <label className="assessment-class-learner-search"><MagnifyingGlass aria-hidden="true" /><input value={learnerQuery} onChange={(event) => setLearnerQuery(event.target.value)} placeholder="Search name, ID, group…" aria-label="Search selected students" /></label>
          <div className="assessment-class-learner-columns" role="row"><span role="columnheader">Name</span><span role="columnheader">Student ID</span><span role="columnheader">Group</span><span role="columnheader">Subgroup</span></div>
          <ul>{filteredLearners.map((learner) => <li key={learner.id}><span className="assessment-class-learner-avatar" aria-hidden="true">{(learner.displayName ?? 'L').trim().charAt(0).toUpperCase()}</span><div className="assessment-class-learner-data"><strong data-label="Name">{learner.displayName ?? 'Unnamed learner'}</strong><span data-label="Student ID">{learner.studentId || '—'}</span><span data-label="Group">{learner.group || '—'}</span><span data-label="Subgroup">{learner.subgroup || '—'}</span></div></li>)}{filteredLearners.length === 0 ? <li className="assessment-class-learner-empty">No selected students match “{learnerQuery.trim()}”.</li> : null}</ul>
        </section>
        <Link to={`/admin/assessments/courses/${courseId}/classes/${classId}/edit`}><UsersThree aria-hidden="true" /> Manage roster rules</Link>
      </section>
      <section className="assessment-class-slides-card"><header><FolderOpen aria-hidden="true" /><div><h2>Slide set</h2><p>The saved folder is used when Classroom starts.</p></div></header>
        {savedFolder ? <>
          <div className="assessment-class-folder-summary"><span><small>Selected folder</small><strong>{savedFolder.folder.name}</strong></span><button type="button" onClick={openFolderBrowser}>Change folder</button></div>
          <div className="assessment-class-slide-preview"><div><FolderOpen aria-hidden="true" /><strong>{savedFolder.slides.length} {savedFolder.slides.length === 1 ? 'slide' : 'slides'}</strong></div><div>{savedFolder.slides.slice(0, 4).map((slide) => slideThumbnail(slide) ? <img key={slide.id} src={slideThumbnail(slide) ?? undefined} alt={slide.displayName} /> : <span key={slide.id} title={slide.displayName}><FolderOpen aria-hidden="true" /></span>)}{savedFolder.slides.length > 4 ? <em>+{savedFolder.slides.length - 4}</em> : null}</div></div>
          <Link className="assessment-class-library-link" to={`/admin?folderId=${encodeURIComponent(savedFolder.folder.id)}`}>View in Slide library <ArrowSquareOut aria-hidden="true" /></Link>
        </> : <button className="assessment-class-folder-empty" type="button" onClick={openFolderBrowser}><FolderOpen aria-hidden="true" /><span><strong>Choose a slide folder</strong><small>Browse folders and select the complete teaching set.</small></span></button>}
        {message ? <p className="assessment-inline-status" role="status">{message}</p> : null}
        <footer className="assessment-classroom-action"><span>{savedFolder ? `${savedFolder.slides.length} slides ready` : 'Choose a slide set first'}</span>{classroomEnabled && classroomUrl ? <Link className="assessment-primary assessment-start-classroom" to={classroomUrl}><ChalkboardTeacher aria-hidden="true" /> Start classroom</Link> : <button className="assessment-primary assessment-start-classroom" type="button" disabled title={!classroomEnabled ? 'Classroom is not enabled for this server.' : 'Choose a slide folder first.'}><ChalkboardTeacher aria-hidden="true" /> Start classroom</button>}</footer>
      </section>
    </div>
    <section className="assessment-class-assessments" aria-labelledby="class-assessments-heading">
      <header><div className="assessment-class-assessments-title"><ClipboardText aria-hidden="true" /><div><h2 id="class-assessments-heading">Assessments</h2><p>Assessments created here stay synchronized with the Assessment workspace.</p></div></div><div className="assessment-class-assessment-actions"><button className="assessment-primary" type="button" onClick={() => void createAssessment()}><Plus aria-hidden="true" /> Create assessment</button></div></header>
      <section className="assessment-class-report-snapshot" aria-labelledby="class-report-snapshot-heading">
        <header><div><ChartBar aria-hidden="true" /><span><strong id="class-report-snapshot-heading">Report snapshot</strong><small>Choose an assessment for its latest response summary.</small></span></div><label><span>Assessment</span><select value={selectedReportDraftId} onChange={(event) => setSelectedReportDraftId(event.target.value)}><option value="">Choose an assessment</option>{drafts.map((draft) => { const administration = latestAdministrationByDraft.get(draft.id); return <option key={draft.id} value={draft.id}>{draft.title} · {administration?.status ?? 'draft'}</option> })}</select></label></header>
        {!selectedReportDraftId || !selectedAdministration ? <p>{selectedReportDraft ? 'Publish this assessment to populate its report.' : 'Create an assessment to begin collecting responses.'}</p> : null}
        {reportState === 'loading' ? <p role="status">Loading report snapshot…</p> : null}
        {reportState === 'error' ? <p role="alert">The report snapshot could not be loaded.</p> : null}
        {report ? <div className="assessment-class-report-snapshot-body"><div className="assessment-class-report-metrics"><article><strong>{report.summary.responses}</strong><span>Responses</span></article><article><strong>{Math.round(Number(report.summary.completionRate) * 100)}%</strong><span>Completion</span></article><article><strong>{report.summary.averagePoints}</strong><span>Average points</span></article><article><strong>{report.summary.needsGrading}</strong><span>Needs grading</span></article></div><Link to={responsesUrl(selectedReportDraftId)}><ChartBar aria-hidden="true" /> Open full report</Link></div> : null}
      </section>
      <div className="assessment-table-wrap assessment-class-assessment-list"><table className="assessment-table"><caption className="visually-hidden">Class assessments</caption><thead><tr><th>Assessment</th><th>Activity</th><th><span className="visually-hidden">Actions</span></th></tr></thead><tbody>{drafts.map((draft) => {
        const administration = latestAdministrationByDraft.get(draft.id)
        const status = draft.status === 'archived' ? 'archived' : administration?.status === 'open' || administration?.status === 'closed' ? administration.status : 'draft'
        const expected = administration?.expectedParticipants ?? (administration ? rosterCount : null)
        const completed = administration?.completedParticipants ?? 0
        const completionPercent = expected && expected > 0 ? Math.min(100, Math.round((completed / expected) * 100)) : 0
        const editUrl = `/admin/assessments/${draft.id}?classId=${encodeURIComponent(classId)}&courseId=${encodeURIComponent(courseId)}`
        const archived = draft.status === 'archived'
        return <tr key={draft.id} className={archived ? 'assessment-row--archived' : undefined}>
          <td className="assessment-cell-assessment"><InlineAssessmentTitle draft={draft} version={administration?.version ?? 0} showDirectory={false} disabled={archived} onOpen={() => navigate(editUrl)} onSaved={(saved) => renamedAssessment(draft.title, saved)} onError={setMessage} /></td>
          <td className="assessment-cell-activity"><div className="assessment-activity-grid">
            <label className="assessment-activity-item assessment-status-control"><span className="assessment-activity-label">Status</span><select aria-label={`Status for ${draft.title}`} className="assessment-status" value={status} disabled={draft.status === 'archived' || busyAdministrationId === administration?.id} onChange={(event) => { if (administration) void changeAssessmentStatus(administration, event.target.value as 'draft' | 'open' | 'closed') }}><option value="draft">Draft</option><option value="open" disabled={!administration}>Open</option><option value="closed" disabled={!administration}>Closed</option>{draft.status === 'archived' ? <option value="archived">Archived</option> : null}</select></label>
            <div className="assessment-activity-item assessment-completion-item"><div className="assessment-completion-ring" role="img" aria-label={expected !== null ? `${completed} of ${expected} learners completed, ${completionPercent}%` : `${administration?.responses ?? 0} responses, 0% completion`}><svg viewBox="0 0 44 44" aria-hidden="true"><circle className="assessment-completion-track" cx="22" cy="22" r="18" /><circle className="assessment-completion-value" cx="22" cy="22" r="18" pathLength="100" strokeDasharray={`${completionPercent} 100`} /></svg><strong>{completionPercent}%</strong></div><div className="assessment-completion-copy"><span className="assessment-activity-label">{expected !== null ? 'Completion' : 'Responses'}</span><strong>{expected !== null ? `${completed} of ${expected}` : (administration?.responses ?? 0)}</strong></div></div>
            <div className="assessment-activity-item"><span className="assessment-activity-label">Modified</span><strong>{administration ? new Date(administration.createdAt).toLocaleDateString() : 'Unpublished'}</strong></div>
          </div></td>
          <td className="assessment-cell-actions"><div className="assessment-row-actions"><button type="button" aria-label={`Preview ${draft.title}`} title={archived ? 'Restore this assessment before previewing it' : 'Preview assessment'} disabled={archived} onClick={() => void showAssessmentPreview(draft)}><Eye aria-hidden="true" /></button><button type="button" aria-label={`Duplicate ${draft.title}, revision ${draft.revision}`} title={archived ? 'Restore this assessment before duplicating it' : 'Duplicate assessment'} disabled={archived} onClick={() => void duplicateAssessment(draft)}><Copy aria-hidden="true" /></button>{archived ? <button className="assessment-restore-button" type="button" aria-label={`Restore ${draft.title}`} title="Restore assessment" onClick={() => void restoreAssessment(draft)}><ArrowCounterClockwise aria-hidden="true" /></button> : <button type="button" aria-label={`Archive ${draft.title}, revision ${draft.revision}`} title="Archive assessment" onClick={() => void archiveAssessment(draft)}><Archive aria-hidden="true" /></button>}{archived ? <button type="button" aria-label={`View report for ${draft.title}`} title="Restore this assessment before viewing its report" disabled><ChartBar aria-hidden="true" /></button> : <Link to={responsesUrl(draft.id)} aria-label={`View report for ${draft.title}`} title="Open assessment responses"><ChartBar aria-hidden="true" /></Link>}</div></td>
        </tr>
      })}</tbody></table>{drafts.length === 0 ? <div className="assessment-class-assessment-empty"><ClipboardText aria-hidden="true" /><h3>No class assessments yet</h3><p>Create an assessment here; it will also appear in the Assessment workspace.</p></div> : null}</div>
    </section>
    {preview ? <div className="assessment-preview-backdrop" onMouseDown={() => setPreview(null)}>
      <div className="assessment-drawer" role="dialog" aria-modal="true" aria-label="Learner preview" onMouseDown={(event) => event.stopPropagation()}>
        <header className="assessment-preview-header"><div className="assessment-preview-header-copy"><span>Learner preview</span><h2>{preview.title}</h2><p>Try the questions · answers are temporary and cannot be submitted.</p></div><div className="assessment-preview-header-actions"><button className="assessment-preview-reset" type="button" aria-label="Reset preview answers" title="Reset preview answers" onClick={() => setPreviewResetKey((key) => key + 1)}><ArrowCounterClockwise aria-hidden="true" /></button><button className="assessment-preview-close" type="button" autoFocus aria-label="Close preview" title="Close preview" onClick={() => setPreview(null)}><X aria-hidden="true" /></button></div></header>
        <div className="assessment-preview-body" key={previewResetKey} aria-label="Interactive learner preview">{assessmentItems(preview).length ? assessmentItems(preview).map((item, index) => <LearnerPreviewItem key={item.id} item={item} index={index} />) : <div className="assessment-preview-empty"><Eye aria-hidden="true" /><h3>No questions to preview</h3><p>Add a question to see the learner experience.</p></div>}</div>
      </div>
    </div> : null}
    {changingFolder ? <div className="assessment-folder-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeFolderBrowser() }}><section className="assessment-folder-dialog" role="dialog" aria-modal="true" aria-labelledby="folder-dialog-heading"><header><div><p className="assessment-kicker">Slide library</p><h2 id="folder-dialog-heading">Choose a folder</h2><p>Select a folder to include every slide in it and its subfolders.</p></div><button type="button" aria-label="Close folder browser" onClick={closeFolderBrowser}><X aria-hidden="true" /></button></header><div className="assessment-folder-dialog-tools"><nav aria-label="Current folder"><button type="button" aria-label="Slide library root" onClick={() => { setFolderQuery(''); setFolderBrowserParentId(null) }}><House aria-hidden="true" /></button>{folderPath.map((folder) => <span key={folder.id}><CaretRight aria-hidden="true" /><button type="button" onClick={() => { setFolderQuery(''); setFolderBrowserParentId(folder.id) }}>{folder.name}</button></span>)}</nav><label className="assessment-folder-search"><MagnifyingGlass aria-hidden="true" /><input autoFocus value={folderQuery} onChange={(event) => setFolderQuery(event.target.value)} placeholder="Search all folders" aria-label="Search folders" /></label></div><div className="assessment-folder-browser" role="listbox" aria-label="Slide folders">{displayedFolderOptions.map((option) => <div className="assessment-folder-card" key={option.folder.id}><button className="assessment-folder-card-select" type="button" role="option" aria-selected={draftFolderId === option.folder.id} disabled={!option.slides.length} onClick={() => setDraftFolderId(option.folder.id)}><span className="assessment-folder-card-icon"><FolderOpen aria-hidden="true" /></span><span className="assessment-folder-card-copy"><strong>{option.folder.name}</strong>{folderQuery ? <em>{folderPathLabels.get(option.folder.id)}</em> : null}<small>{option.slides.length} {option.slides.length === 1 ? 'slide' : 'slides'}{option.folder.hasChildren ? ' · Contains subfolders' : ''}</small></span><span className="assessment-folder-card-preview">{option.slides.slice(0, 3).map((slide) => slideThumbnail(slide) ? <img key={slide.id} src={slideThumbnail(slide) ?? undefined} alt="" /> : <i key={slide.id} />)}</span>{draftFolderId === option.folder.id ? <Check aria-hidden="true" /> : null}</button>{option.folder.hasChildren ? <button className="assessment-folder-card-open" type="button" aria-label={`Open ${option.folder.name}`} onClick={() => { setFolderQuery(''); setFolderBrowserParentId(option.folder.id) }}>Open <CaretRight aria-hidden="true" /></button> : null}</div>)}{visibleFolderOptions.length > folderResultPageSize ? <div className="assessment-folder-more" role="presentation"><button type="button" disabled={folderResultPage === 0} onClick={() => setFolderResultPage((page) => Math.max(0, page - 1))}>Previous</button><span>{folderResultStart + 1}–{Math.min(folderResultStart + folderResultPageSize, visibleFolderOptions.length)} of {visibleFolderOptions.length}</span><button type="button" disabled={folderResultStart + folderResultPageSize >= visibleFolderOptions.length} onClick={() => setFolderResultPage((page) => page + 1)}>Next 32</button></div> : null}{visibleFolderOptions.length === 0 ? <p>{folderQuery ? 'No folders match your search.' : 'This folder has no subfolders.'}</p> : null}</div><footer><button type="button" onClick={closeFolderBrowser}>Cancel</button><button className="assessment-primary" type="button" disabled={!draftFolderId || savingFolder || draftFolderId === savedFolderId} onClick={() => void saveFolder()}>{savingFolder ? 'Saving…' : 'Use this folder'}</button></footer></section></div> : null}
  </div></>
}
