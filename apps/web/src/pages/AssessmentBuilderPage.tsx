import { ArrowCounterClockwise, Check, Desktop, DeviceMobile, DeviceTablet, Eye, PaperPlaneTilt, X } from '@phosphor-icons/react'
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'

import {
  createAssessmentDraft,
  getAssessmentDraft,
  importAssessmentQuestions,
  listAssessmentClasses,
  listAssessmentDrafts,
  migrateAssessmentDraftV2,
  previewAssessmentDraft,
  publishAssessmentDraft,
  saveAssessmentDraft,
} from '../assessment/api'
import { cacheAssessmentDraft, readCachedAssessmentDraft } from '../assessment/draftCache'
import { AssessmentToolbar } from '../components/assessment/AssessmentChrome'
import { AssessmentQuestionCanvas } from '../components/assessment/AssessmentQuestionCanvas'
import { AssessmentLearnerPreview } from '../components/assessment/AssessmentLearnerPreview'
import { AssessmentSectionCanvas, type AssessmentTemplateSummary } from '../components/assessment/AssessmentSectionCanvas'
import { AutoGrowTextarea } from '../components/assessment/AutoGrowTextarea'
import { assessmentItems, isAssessmentV2, type AssessmentDocument, type AssessmentDraft } from '../assessment/types'
import { questionTypesByType } from '../assessment/questionTypes'
import './assessment.css'

const AssessmentReportPage = lazy(() => import('./AssessmentReportPage').then((module) => ({ default: module.AssessmentReportPage })))

export function AssessmentBuilderPage() {
  const { draftId = '' } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [draft, setDraft] = useState<AssessmentDraft | null>(null)
  const [loadRevision, setLoadRevision] = useState(0)
  const requestedTab = searchParams.get('tab')
  const tab: 'questions' | 'settings' | 'responses' = requestedTab === 'responses' || requestedTab === 'settings' ? requestedTab : 'questions'
  const [saveState, setSaveState] = useState('Loading…')
  const [publishOpen, setPublishOpen] = useState(false)
  const [mode, setMode] = useState<'practice' | 'formative' | 'quiz'>('formative')
  const [cohortId, setCohortId] = useState(() => searchParams.get('classId') ?? '')
  const [classIds, setClassIds] = useState<Set<string>>(() => new Set(searchParams.get('classId') ? [searchParams.get('classId')!] : []))
  const [duration, setDuration] = useState(3600)
  const [attempts, setAttempts] = useState(2)
  const [accessCode, setAccessCode] = useState('')
  const [classes, setClasses] = useState<Array<{ id: string; name: string }>>([])
  const [preview, setPreview] = useState<AssessmentDocument | null>(null)
  const [previewNotice, setPreviewNotice] = useState('')
  const [previewWidth, setPreviewWidth] = useState<1200 | 768 | 390>(1200)
  const [previewSeed, setPreviewSeed] = useState(0)
  const [publishedLink, setPublishedLink] = useState('')
  const [publishedAdministrations, setPublishedAdministrations] = useState<Array<{ id: string; publicId: string; classId: string | null; accessCode: string | null }>>([])
  const [manualAcceptance, setManualAcceptance] = useState(true)
  const [closesAt, setClosesAt] = useState('')
  const [responseLimit, setResponseLimit] = useState('')
  const [closedMessage, setClosedMessage] = useState('This assignment is no longer accepting responses.')
  const [releaseTiming, setReleaseTiming] = useState<'immediate' | 'manual'>('manual')
  const [releaseFields, setReleaseFields] = useState({ score: true, answers: false, authored: false, manual: false, annotations: false })
  const [importOpen, setImportOpen] = useState(false)
  const [sources, setSources] = useState<AssessmentDraft[]>([])
  const [sourceId, setSourceId] = useState('')
  const [importIds, setImportIds] = useState<Set<string>>(new Set())
  const [importStatus, setImportStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [importSubmitting, setImportSubmitting] = useState(false)
  const [importMessage, setImportMessage] = useState('')
  const [importQuery, setImportQuery] = useState('')
  const [migrationBusy, setMigrationBusy] = useState(false)
  const revisionRef = useRef(0)
  const acknowledgedDocumentRef = useRef<AssessmentDocument | null>(null)
  const items = useMemo(() => draft ? assessmentItems(draft.document) : [], [draft])
  const questions = useMemo(() => items.filter((item) => item.type !== 'section-information'), [items])
  const totalPoints = useMemo(() => items.reduce((total, item) => total + (questionTypesByType[item.type].supportsScoring ? Number(item.points || 0) || 0 : 0), 0), [items])

  useEffect(() => {
    let cancelled = false
    setSaveState('Loading…')
    void Promise.all([getAssessmentDraft(draftId), readCachedAssessmentDraft(draftId)])
      .then(([server, cached]) => {
        if (cancelled) return
        const recovered = cached && cached.revision > server.revision
        const selected = recovered ? cached : server
        revisionRef.current = server.revision
        acknowledgedDocumentRef.current = recovered ? null : server.document
        setDraft(selected)
        setMode(selected.document.settings.mode ?? 'formative')
        if (isAssessmentV2(selected.document)) {
          setReleaseTiming(selected.document.release?.timing ?? 'manual')
          setReleaseFields({
            score: selected.document.release?.showScore ?? true,
            answers: selected.document.release?.showAnswers ?? false,
            authored: selected.document.release?.showAuthoredFeedback ?? false,
            manual: selected.document.release?.showManualFeedback ?? false,
            annotations: selected.document.release?.showAnnotations ?? false,
          })
        }
        setSaveState(recovered
          ? 'Recovered local edits'
          : 'All changes saved')
      })
      .catch(() => { if (!cancelled) setSaveState('Unable to open draft') })
    return () => { cancelled = true }
  }, [draftId, loadRevision])

  useEffect(() => {
    if (!draft) return
    if (acknowledgedDocumentRef.current === draft.document) {
      acknowledgedDocumentRef.current = null
      return
    }
    setSaveState('Saving…')
    void cacheAssessmentDraft(draft)
    const timer = window.setTimeout(() => {
      const submittedDocument = draft.document
      void saveAssessmentDraft(draft.id, revisionRef.current, submittedDocument)
        .then((saved) => {
          revisionRef.current = saved.revision
          setDraft((current) => {
            if (current && current.document !== submittedDocument) {
              return { ...current, revision: saved.revision }
            }
            acknowledgedDocumentRef.current = saved.document
            return saved
          })
          void cacheAssessmentDraft(saved)
          setSaveState('All changes saved')
        })
        .catch(() => setSaveState('Conflict: reload or duplicate'))
    }, 750)
    return () => window.clearTimeout(timer)
  }, [draft])

  function updateDocument(update: (document: AssessmentDocument) => AssessmentDocument) {
    setDraft((current) => current ? { ...current, document: update(current.document) } : current)
  }

  function selectTab(value: typeof tab) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value === 'questions') next.delete('tab')
      else next.set('tab', value)
      return next
    })
  }

  function updateMode(value: 'practice' | 'formative' | 'quiz') {
    setMode(value)
    setAttempts(value === 'formative' ? 2 : 1)
    updateDocument((document) => ({ ...document, settings: { ...document.settings, mode: value } }))
  }

  function updateReleaseField(field: keyof typeof releaseFields, value: boolean) {
    setReleaseFields((current) => ({ ...current, [field]: value }))
    const property = {
      score: 'showScore',
      answers: 'showAnswers',
      authored: 'showAuthoredFeedback',
      manual: 'showManualFeedback',
      annotations: 'showAnnotations',
    }[field]
    updateDocument((document) => isAssessmentV2(document) ? {
      ...document,
      release: { ...document.release, [property]: value },
    } : document)
  }

  function openPublish() {
    setPublishOpen(true)
    void listAssessmentClasses().then((result) => setClasses(result.items))
  }

  async function showPreview() {
    if (!draft) return
    setPreview(draft.document)
    setPreviewNotice('')
    try {
      await previewAssessmentDraft(draft.id)
    } catch {
      setPreviewNotice('Previewing the current draft. Publishing validation is still required.')
    }
  }

  async function publish() {
    if (!draft) return
    const result = await publishAssessmentDraft(draft.id, {
      mode, durationSeconds: duration, maxAttempts: attempts,
      ...(isAssessmentV2(draft.document) ? { classIds: [...classIds] } : cohortId ? { cohortId } : {}), ...(accessCode ? { accessCode } : {}),
      collection: { manualAcceptance, ...(closesAt ? { closesAt: new Date(closesAt).toISOString() } : {}), ...(responseLimit ? { responseLimit: Number(responseLimit) } : {}), closedMessage },
      releasePolicy: { timing: releaseTiming, showScore: releaseFields.score, showAnswers: releaseFields.answers, showAuthoredFeedback: releaseFields.authored, showManualFeedback: releaseFields.manual, showAnnotations: releaseFields.annotations },
    })
    setPublishedLink(result.publicId ? `${location.origin}/assessment/${result.publicId}` : '')
    setPublishedAdministrations(result.administrations ?? [])
  }

  async function openImport() {
    setImportOpen(true)
    setImportStatus('loading')
    setImportMessage('')
    setSourceId('')
    setImportIds(new Set())
    try {
      const result = await listAssessmentDrafts()
      setSources(result.items.filter((item) => item.id !== draft?.id))
      setImportStatus('ready')
    } catch {
      setSources([])
      setImportStatus('error')
      setImportMessage('Could not load assessment drafts. Try again.')
    }
  }

  function templateSummary(candidate: AssessmentDraft): AssessmentTemplateSummary | null {
    if (!isAssessmentV2(candidate.document)) return null
    return {
      id: candidate.id,
      name: candidate.title.replace(/^Template —\s*/, ''),
      document: candidate.document,
    }
  }

  async function listTemplates() {
    const result = await listAssessmentDrafts()
    return result.items
      .filter((candidate) => candidate.id !== draft?.id && candidate.title.startsWith('Template — '))
      .map(templateSummary)
      .filter((candidate): candidate is AssessmentTemplateSummary => candidate !== null)
  }

  async function createTemplate(name: string) {
    if (!draft) throw new Error('ASSESSMENT_DRAFT_UNAVAILABLE')
    const title = `Template — ${name.trim()}`
    const document = structuredClone(draft.document)
    document.title = title
    const created = await createAssessmentDraft(title, document, draft.courseId ? {
      courseId: draft.courseId,
      ...(draft.classId ? { classId: draft.classId } : {}),
    } : undefined)
    const summary = templateSummary(created)
    if (!summary) throw new Error('ASSESSMENT_TEMPLATE_UNSUPPORTED')
    return summary
  }

  async function importQuestions() {
    if (!draft || !sourceId || importIds.size === 0) return
    setImportSubmitting(true)
    setImportMessage('')
    try {
      const saved = await importAssessmentQuestions(draft.id, sourceId, [...importIds], revisionRef.current)
      revisionRef.current = saved.revision
      acknowledgedDocumentRef.current = saved.document
      setDraft(saved)
      setImportOpen(false)
      setImportIds(new Set())
      setSaveState('All changes saved')
    } catch {
      setImportMessage('Questions could not be imported. Refresh the source and try again.')
    } finally {
      setImportSubmitting(false)
    }
  }

  async function migrateToV2() {
    if (!draft || isAssessmentV2(draft.document)) return
    setMigrationBusy(true)
    try {
      const migrated = await migrateAssessmentDraftV2(draft.id, draft.revision)
      navigate(`/admin/assessments/${migrated.id}`, { replace: true })
    } finally {
      setMigrationBusy(false)
    }
  }

  if (!draft) return <main className="assessment-loading">
    <div className="assessment-load-state">
      <p role="status">{saveState}</p>
      {saveState === 'Unable to open draft'
        ? <button type="button" className="assessment-primary" onClick={() => setLoadRevision((current) => current + 1)}>Retry</button>
        : null}
    </div>
  </main>

  return <div className="assessment-builder">
    <AssessmentToolbar title={draft.document.title} />
    <h1 className="visually-hidden">{draft.document.title}</h1>
    <section className="assessment-studio-header" aria-label="Assessment authoring commands">
      <div className="assessment-studio-identity">
        <label>
          <span className="visually-hidden">Assessment name</span>
          <AutoGrowTextarea className="assessment-studio-title" aria-label="Assessment name" maxLength={200} value={draft.document.title} onChange={(event) => updateDocument((document) => ({ ...document, title: event.target.value }))} />
        </label>
        <label className="assessment-studio-description">
          <span className="visually-hidden">Assessment description</span>
          <textarea aria-label="Assessment description" rows={2} maxLength={2000} placeholder="Add instructions or context for learners" value={draft.document.description ?? ''} onChange={(event) => updateDocument((document) => ({ ...document, description: event.target.value }))} />
        </label>
      </div>
      <div className="assessment-studio-meta">
        <span><strong>{questions.length}</strong> {questions.length === 1 ? 'question' : 'questions'}</span>
        <span><strong>{totalPoints}</strong> {totalPoints === 1 ? 'point' : 'points'}</span>
        <span className="assessment-save-state" data-state={saveState === 'All changes saved' ? 'saved' : 'pending'} aria-live="polite"><Check aria-hidden="true" /> {saveState}</span>
      </div>
      <div className="assessment-studio-actions">
        {!isAssessmentV2(draft.document) ? <button type="button" disabled={migrationBusy} onClick={() => void migrateToV2()}>{migrationBusy ? 'Upgrading…' : 'Upgrade to sections'}</button> : null}
        <button className="assessment-primary" type="button" onClick={openPublish}><PaperPlaneTilt aria-hidden="true" />Publish</button>
      </div>
      <div className="assessment-tabs" role="tablist" aria-label="Assessment builder">
        {(['questions', 'responses', 'settings'] as const).map((value) =>
          <button key={value} role="tab" aria-selected={tab === value} onClick={() => selectTab(value)}>
            {value[0].toUpperCase() + value.slice(1)}
          </button>)}
      </div>
    </section>
    {tab === 'questions' ? isAssessmentV2(draft.document) ? <AssessmentSectionCanvas
      document={draft.document}
      draftId={draft.id}
      mediaScopeLabel={draft.className ?? draft.courseName ?? 'this lesson'}
      onDocumentChange={(update) => updateDocument((document) => isAssessmentV2(document) ? update(document) : document)}
      onImport={() => void openImport()}
      onPreview={() => void showPreview()}
      onCreateTemplate={createTemplate}
      onListTemplates={listTemplates}
    /> : <AssessmentQuestionCanvas
      document={draft.document}
      draftId={draft.id}
      mediaScopeLabel={draft.className ?? draft.courseName ?? 'this lesson'}
      onDocumentChange={updateDocument}
      onImport={() => void openImport()}
      onPreview={() => void showPreview()}
    /> : null}
    {tab === 'settings' ? <main className="assessment-settings assessment-studio-settings">
      <header className="assessment-settings-intro"><span>Assignment controls</span><h2>Settings</h2><p>Configure how learners experience, submit, and review this assignment. These controls are also reflected when you publish.</p></header>
      <section><div className="assessment-settings-heading"><div><h3>Response mode</h3><p>Choose the identity, storage, and grading model.</p></div></div>
      <div className="assessment-mode-grid">
        <label><input type="radio" name="mode" value="practice" checked={mode === 'practice'} onChange={() => updateMode('practice')} />
          <strong>Practice</strong><span>Anonymous, browser-local, immediate feedback.</span></label>
        <label><input type="radio" name="mode" value="formative" checked={mode === 'formative'} onChange={() => updateMode('formative')} />
          <strong>Formative</strong><span>Anonymous aggregate or rostered gradebook.</span></label>
        <label><input type="radio" name="mode" value="quiz" checked={mode === 'quiz'} onChange={() => updateMode('quiz')} />
          <strong>Quiz / Test</strong><span>Roster, ID plus code, deliberate release.</span></label>
      </div></section>
      {isAssessmentV2(draft.document) ? <>
        <section><div className="assessment-settings-heading"><div><h3>Presentation</h3><p>Control pacing and the learner-facing structure.</p></div></div><div className="assessment-settings-grid"><label>Layout preset<select value={draft.document.presentation.preset ?? 'standard'} onChange={(event) => updateDocument((document) => isAssessmentV2(document) ? { ...document, presentation: { ...document.presentation, preset: event.target.value as 'compact' | 'standard' | 'focus' } } : document)}><option value="compact">Compact</option><option value="standard">Standard</option><option value="focus">Focus</option></select></label><label className="assessment-setting-toggle"><span><strong>Progress indicator</strong><small>Show learners how much remains.</small></span><input type="checkbox" checked={draft.document.presentation.showProgress ?? true} onChange={(event) => updateDocument((document) => isAssessmentV2(document) ? { ...document, presentation: { ...document.presentation, showProgress: event.target.checked } } : document)} /></label><label className="assessment-setting-toggle"><span><strong>Section titles</strong><small>Keep authored section context visible.</small></span><input type="checkbox" checked={draft.document.presentation.showSectionTitles ?? true} onChange={(event) => updateDocument((document) => isAssessmentV2(document) ? { ...document, presentation: { ...document.presentation, showSectionTitles: event.target.checked } } : document)} /></label><label className="assessment-setting-toggle"><span><strong>Shuffle questions</strong><small>Shuffle only within safe contiguous runs.</small></span><input type="checkbox" checked={draft.document.settings.shuffleQuestions ?? false} onChange={(event) => updateDocument((document) => isAssessmentV2(document) ? { ...document, settings: { ...document.settings, shuffleQuestions: event.target.checked } } : document)} /></label></div></section>
        <section><div className="assessment-settings-heading"><div><h3>Responses</h3><p>Set availability, limits, and submission rules for the next publication.</p></div><span>Applied on publish</span></div><div className="assessment-settings-grid assessment-settings-grid--two"><label className="assessment-setting-toggle"><span><strong>Accept responses</strong><small>Turn off to block new attempts while active learners finish.</small></span><input type="checkbox" checked={manualAcceptance} onChange={(event) => setManualAcceptance(event.target.checked)} /></label><label>Maximum attempts<input type="number" min="1" max="3" value={attempts} onChange={(event) => setAttempts(Number(event.target.value))} /></label><label>Time limit (minutes)<input type="number" min="1" max="240" value={duration / 60} onChange={(event) => setDuration(Number(event.target.value) * 60)} /></label><label>Response limit<input type="number" min="1" max="500" placeholder="No limit" value={responseLimit} onChange={(event) => setResponseLimit(event.target.value)} /></label><label>Close automatically<input type="datetime-local" value={closesAt} onChange={(event) => setClosesAt(event.target.value)} /></label>{mode === 'quiz' ? <label>Access code<input value={accessCode} placeholder="Generate automatically when blank" onChange={(event) => setAccessCode(event.target.value)} /></label> : null}<label className="assessment-setting-wide">Closed message<textarea maxLength={1000} value={closedMessage} onChange={(event) => setClosedMessage(event.target.value)} /></label></div></section>
        <section><div className="assessment-settings-heading"><div><h3>Results and feedback</h3><p>Choose when results appear and what learners may review.</p></div></div><div className="assessment-settings-grid assessment-settings-grid--two"><label>Release timing<select value={releaseTiming} onChange={(event) => { const timing = event.target.value as 'immediate' | 'manual'; setReleaseTiming(timing); updateDocument((document) => isAssessmentV2(document) ? { ...document, release: { ...document.release, timing } } : document) }}><option value="manual">Release manually</option><option value="immediate">Immediately when fully auto-graded</option></select></label>{Object.entries({ score: ['Score', 'Show earned and available points'], answers: ['Correct answers', 'Reveal answer keys and accepted answers'], authored: ['Authored feedback', 'Show correct and incorrect explanations'], manual: ['Manual feedback', 'Show teacher grading comments'], annotations: ['Released annotations', 'Show sanitized teaching overlays'] } as const).map(([key, [label, help]]) => <label className="assessment-setting-toggle" key={key}><span><strong>{label}</strong><small>{help}</small></span><input type="checkbox" checked={releaseFields[key as keyof typeof releaseFields]} onChange={(event) => updateReleaseField(key as keyof typeof releaseFields, event.target.checked)} /></label>)}</div></section>
        <section className="assessment-settings-health"><div className="assessment-settings-heading"><div><h3>Blueprint health</h3><p>Publication checks for pacing and learner guidance.</p></div></div><ul>{draft.document.sections.flatMap((section) => [section.items.length > 25 ? `${section.title}: more than 25 questions` : '', ...section.items.map((item) => item.type === 'diagnostic-field' && item.prompt.length > 200 && !item.helpText ? `${item.prompt.slice(0, 48)}: add learner help` : '')]).filter(Boolean).map((warning) => <li key={warning}>{warning}</li>)}</ul>{!draft.document.sections.some((section) => section.items.length > 25 || section.items.some((item) => item.type === 'diagnostic-field' && item.prompt.length > 200 && !item.helpText)) ? <p className="assessment-settings-ready"><Check aria-hidden="true" /> Blueprint thresholds are healthy.</p> : null}</section>
      </> : null}
    </main> : null}
    {tab === 'responses' ? <Suspense fallback={<main className="assessment-main"><p role="status">Loading responses…</p></main>}><AssessmentReportPage embedded /></Suspense> : null}
    {preview ? <div className="assessment-preview-backdrop" onMouseDown={() => setPreview(null)}>
      <div className="assessment-drawer assessment-preview-drawer" role="dialog" aria-modal="true" aria-label="Learner preview" onMouseDown={(event) => event.stopPropagation()}>
        <header className="assessment-preview-header"><div className="assessment-preview-header-copy"><span>Learner preview</span><h2>{preview.title}</h2></div><div className="assessment-preview-header-actions"><button className="assessment-preview-close" type="button" autoFocus aria-label="Close preview" onClick={() => setPreview(null)}><X aria-hidden="true" /></button></div></header>
        <div className="assessment-preview-device-controls" aria-label="Preview size">
          <button type="button" aria-label="Desktop preview" title="Desktop preview" aria-pressed={previewWidth === 1200} onClick={() => setPreviewWidth(1200)}><Desktop aria-hidden="true" /></button>
          <button type="button" aria-label="Tablet preview" title="Tablet preview" aria-pressed={previewWidth === 768} onClick={() => setPreviewWidth(768)}><DeviceTablet aria-hidden="true" /></button>
          <button type="button" aria-label="Mobile preview" title="Mobile preview" aria-pressed={previewWidth === 390} onClick={() => setPreviewWidth(390)}><DeviceMobile aria-hidden="true" /></button>
          <button type="button" aria-label="Reset preview" title="Reset preview" onClick={() => setPreviewSeed((seed) => seed + 1)}><ArrowCounterClockwise aria-hidden="true" /></button>
        </div>
        {previewNotice ? <p className="assessment-preview-notice" role="status">{previewNotice}</p> : null}
        <div className="assessment-preview-stage"><div className="assessment-preview-body" style={{ maxWidth: previewWidth }} aria-label="Assignment preview questions">{assessmentItems(preview).length ? <AssessmentLearnerPreview document={preview} seed={`preview-${previewSeed}`} /> : <div className="assessment-preview-empty"><Eye aria-hidden="true" /><h3>No questions to preview</h3><p>Add a question to see the assignment preview.</p></div>}</div></div>
      </div>
    </div> : null}
    {publishOpen ? <div className="assessment-preview-backdrop" onMouseDown={() => setPublishOpen(false)}>
      <div className="assessment-drawer assessment-builder-drawer" role="dialog" aria-modal="true" aria-label="Publish assessment" onMouseDown={(event) => event.stopPropagation()}>
        <header className="assessment-preview-header"><div className="assessment-preview-header-copy"><span>Publish settings</span><h2>{draft.document.title}</h2><p>Choose the learner mode, timing, and access controls.</p></div><div className="assessment-preview-header-actions"><button className="assessment-preview-close" type="button" autoFocus aria-label="Close publish settings" onClick={() => setPublishOpen(false)}><X aria-hidden="true" /></button></div></header>
        <div className="assessment-builder-drawer-body"><label>Mode<select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}><option value="practice">Practice</option><option value="formative">Formative</option><option value="quiz">Quiz / Test</option></select></label>{mode !== 'practice' ? isAssessmentV2(draft.document) ? <fieldset><legend>Classes</legend>{classes.map((item) => <label key={item.id}><input type="checkbox" checked={classIds.has(item.id)} onChange={() => setClassIds((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })} /> {item.name}</label>)}</fieldset> : <label>Class<select value={cohortId} onChange={(event) => setCohortId(event.target.value)}><option value="">Anonymous formative only</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : null}<label>Duration (minutes)<input type="number" min="1" max="240" value={duration / 60} onChange={(event) => setDuration(Number(event.target.value) * 60)} /></label><label>Attempts<input type="number" min="1" max="3" value={attempts} onChange={(event) => setAttempts(Number(event.target.value))} /></label>{mode === 'quiz' ? <label>Access code<input value={accessCode} placeholder="Leave blank to generate one-time codes" onChange={(event) => setAccessCode(event.target.value)} /></label> : null}<details><summary>Collection settings</summary><label><input type="checkbox" checked={manualAcceptance} onChange={(event) => setManualAcceptance(event.target.checked)} /> Accept new attempts</label><label>Scheduled close<input type="datetime-local" value={closesAt} onChange={(event) => setClosesAt(event.target.value)} /></label><label>Response limit<input type="number" min="1" max="500" value={responseLimit} onChange={(event) => setResponseLimit(event.target.value)} /></label><label>Closed message<textarea maxLength={1000} value={closedMessage} onChange={(event) => setClosedMessage(event.target.value)} /></label></details><details><summary>Learner release</summary><label>Timing<select value={releaseTiming} onChange={(event) => setReleaseTiming(event.target.value as 'immediate' | 'manual')}><option value="manual">Manual release</option><option value="immediate">Immediate when fully auto-graded</option></select></label>{Object.entries({ score: 'Score', answers: 'Correct answers', authored: 'Authored feedback', manual: 'Manual feedback', annotations: 'Released annotations' }).map(([key, label]) => <label key={key}><input type="checkbox" checked={releaseFields[key as keyof typeof releaseFields]} onChange={(event) => setReleaseFields((current) => ({ ...current, [key]: event.target.checked }))} /> {label}</label>)}</details><button className="assessment-primary" type="button" onClick={() => void publish()}>Publish assignment</button>{publishedLink ? <p role="status">Published: <a href={publishedLink}>{publishedLink}</a></p> : null}{publishedAdministrations.map((administration) => { const link = `${location.origin}/assessment/${administration.publicId}`; return <article className="assessment-published-link" key={administration.id}><QRCodeSVG value={link} size={112} level="M" aria-label="Assignment access QR code" /><div><a href={link}>{link}</a>{administration.accessCode ? <strong>One-time access code: {administration.accessCode}</strong> : null}</div></article> })}</div>
      </div>
    </div> : null}
    {importOpen ? <div className="assessment-preview-backdrop" onMouseDown={() => setImportOpen(false)}>
      <div className="assessment-drawer assessment-builder-drawer assessment-import-drawer" role="dialog" aria-modal="true" aria-label="Import assessment" onMouseDown={(event) => event.stopPropagation()}>
        <header className="assessment-preview-header"><div className="assessment-preview-header-copy"><span>Assessment library</span><h2>Import assessment</h2><p>Choose another assessment and copy all or selected questions into this form.</p></div><div className="assessment-preview-header-actions"><button className="assessment-preview-close" type="button" autoFocus aria-label="Close import" onClick={() => setImportOpen(false)}><X aria-hidden="true" /></button></div></header>
        <div className="assessment-builder-drawer-body">{importStatus === 'loading' ? <p role="status">Loading assessments…</p> : null}{importStatus === 'error' ? <div className="assessment-import-state" role="alert"><p>{importMessage}</p><button type="button" onClick={() => void openImport()}>Try again</button></div> : null}{importStatus === 'ready' && sources.length === 0 ? <div className="assessment-import-state"><strong>No source assessments available</strong><p>Create or duplicate another assessment before importing questions.</p></div> : null}{importStatus === 'ready' && sources.length > 0 ? <><label>Source assessment<select value={sourceId} onChange={(event) => { setSourceId(event.target.value); setImportIds(new Set()); setImportQuery('') }}><option value="">Choose an assessment</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}</select></label>{sourceId ? <><div className="assessment-import-tools"><label>Search questions<input type="search" value={importQuery} onChange={(event) => setImportQuery(event.target.value)} /></label><button type="button" onClick={() => { const source = sources.find((candidate) => candidate.id === sourceId); if (source) setImportIds(new Set(assessmentItems(source.document).filter((item) => item.prompt.toLocaleLowerCase().includes(importQuery.trim().toLocaleLowerCase())).map((item) => item.id))) }}>Select all shown</button><button type="button" disabled={importIds.size === 0} onClick={() => setImportIds(new Set())}>Clear</button></div><div className="assessment-import-question-list" aria-label="Questions available to import">{assessmentItems(sources.find((source) => source.id === sourceId)!.document).filter((item) => item.prompt.toLocaleLowerCase().includes(importQuery.trim().toLocaleLowerCase())).map((item) => <label key={item.id}><input type="checkbox" checked={importIds.has(item.id)} onChange={() => setImportIds((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })} /> <span>{item.prompt || 'Untitled question'}</span></label>)}</div></> : <p className="assessment-import-hint">Choose an assessment to review its questions.</p>}{importMessage ? <p role="alert">{importMessage}</p> : null}<button className="assessment-primary" type="button" disabled={importIds.size === 0 || importSubmitting} onClick={() => void importQuestions()}>{importSubmitting ? 'Importing…' : `Import selected${importIds.size ? ` (${importIds.size})` : ''}`}</button></> : null}</div>
      </div>
    </div> : null}
  </div>
}
