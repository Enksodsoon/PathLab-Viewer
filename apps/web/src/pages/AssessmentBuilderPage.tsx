import { Check, Eye, PaperPlaneTilt, X } from '@phosphor-icons/react'
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import {
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
import { AssessmentSectionCanvas } from '../components/assessment/AssessmentSectionCanvas'
import { assessmentItems, isAssessmentV2, type AssessmentDocument, type AssessmentDraft } from '../assessment/types'
import { questionTypesByType } from '../assessment/questionTypes'
import './assessment.css'

const AssessmentReportPage = lazy(() => import('./AssessmentReportPage').then((module) => ({ default: module.AssessmentReportPage })))

export function AssessmentBuilderPage() {
  const { draftId = '' } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [draft, setDraft] = useState<AssessmentDraft | null>(null)
  const requestedTab = searchParams.get('tab')
  const tab: 'description' | 'questions' | 'settings' | 'responses' = requestedTab === 'description' || requestedTab === 'responses' || requestedTab === 'settings' ? requestedTab : 'questions'
  const [saveState, setSaveState] = useState('Loading…')
  const [publishOpen, setPublishOpen] = useState(false)
  const [mode, setMode] = useState<'practice' | 'formative' | 'quiz'>('formative')
  const [cohortId, setCohortId] = useState(() => searchParams.get('classId') ?? '')
  const [duration, setDuration] = useState(3600)
  const [attempts, setAttempts] = useState(2)
  const [accessCode, setAccessCode] = useState('')
  const [classes, setClasses] = useState<Array<{ id: string; name: string }>>([])
  const [preview, setPreview] = useState<AssessmentDocument | null>(null)
  const [previewWidth, setPreviewWidth] = useState<1200 | 768 | 390>(1200)
  const [previewSeed, setPreviewSeed] = useState(0)
  const [publishedLink, setPublishedLink] = useState('')
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
  const totalPoints = useMemo(() => items.reduce((total, item) => total + (questionTypesByType[item.type].supportsScoring ? Number(item.points || 0) || 0 : 0), 0), [items])

  useEffect(() => {
    let cancelled = false
    void Promise.all([getAssessmentDraft(draftId), readCachedAssessmentDraft(draftId)])
      .then(([server, cached]) => {
        if (cancelled) return
        const recovered = cached && cached.revision > server.revision
        const selected = recovered ? cached : server
        revisionRef.current = server.revision
        acknowledgedDocumentRef.current = recovered ? null : server.document
        setDraft(selected)
        setSaveState(recovered
          ? 'Recovered local edits'
          : 'All changes saved')
      })
      .catch(() => { if (!cancelled) setSaveState('Unable to open draft') })
    return () => { cancelled = true }
  }, [draftId])

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

  function openPublish() {
    setPublishOpen(true)
    void listAssessmentClasses().then((result) => setClasses(result.items))
  }

  async function showPreview() {
    if (!draft) return
    const result = await previewAssessmentDraft(draft.id)
    setPreview(result.learnerManifest)
  }

  async function publish() {
    if (!draft) return
    const result = await publishAssessmentDraft(draft.id, {
      mode, durationSeconds: duration, maxAttempts: attempts,
      ...(cohortId ? { cohortId } : {}), ...(accessCode ? { accessCode } : {}),
    })
    setPublishedLink(result.publicId ? `${location.origin}/assessment/${result.publicId}` : '')
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

  if (!draft) return <main className="assessment-loading"><p role="status">{saveState}</p></main>

  return <div className="assessment-builder">
    <AssessmentToolbar title={draft.document.title} />
    <h1 className="visually-hidden">{draft.document.title}</h1>
    <section className="assessment-studio-header" aria-label="Assessment authoring commands">
      <div className="assessment-studio-identity">
        <label>
          <span className="visually-hidden">Assessment name</span>
          <input aria-label="Assessment name" value={draft.document.title} onChange={(event) => updateDocument((document) => ({ ...document, title: event.target.value }))} />
        </label>
      </div>
      <div className="assessment-studio-meta">
        <span><strong>{items.length}</strong> {items.length === 1 ? 'question' : 'questions'}</span>
        <span><strong>{totalPoints}</strong> {totalPoints === 1 ? 'point' : 'points'}</span>
        <span className="assessment-save-state" data-state={saveState === 'All changes saved' ? 'saved' : 'pending'} aria-live="polite"><Check aria-hidden="true" /> {saveState}</span>
      </div>
      <div className="assessment-studio-actions">
        {!isAssessmentV2(draft.document) ? <button type="button" disabled={migrationBusy} onClick={() => void migrateToV2()}>{migrationBusy ? 'Upgrading…' : 'Upgrade to sections'}</button> : null}
        <button type="button" onClick={() => void showPreview()}><Eye aria-hidden="true" />Preview</button>
        <button className="assessment-primary" type="button" onClick={openPublish}><PaperPlaneTilt aria-hidden="true" />Publish</button>
      </div>
      <div className="assessment-tabs" role="tablist" aria-label="Assessment builder">
        {(['description', 'questions', 'responses', 'settings'] as const).map((value) =>
          <button key={value} role="tab" aria-selected={tab === value} onClick={() => selectTab(value)}>
            {value[0].toUpperCase() + value.slice(1)}
          </button>)}
      </div>
    </section>
    {tab === 'description' ? <main className="assessment-description-panel">
      <header><h2>Assessment description</h2><p>Give learners a clear name and short context before they begin.</p></header>
      <label><span>Name</span><input value={draft.document.title} onChange={(event) => updateDocument((document) => ({ ...document, title: event.target.value }))} /></label>
      <label><span>Description</span><textarea aria-label="Description" rows={6} maxLength={2000} placeholder="Describe the scope, learning objectives, or instructions for this assessment." value={draft.document.description ?? ''} onChange={(event) => updateDocument((document) => ({ ...document, description: event.target.value }))} /><small>{(draft.document.description ?? '').length} / 2000 characters</small></label>
    </main> : null}
    {tab === 'questions' ? isAssessmentV2(draft.document) ? <AssessmentSectionCanvas
      document={draft.document}
      onDocumentChange={(update) => updateDocument((document) => isAssessmentV2(document) ? update(document) : document)}
      onImport={() => void openImport()}
      onPreview={() => void showPreview()}
    /> : <AssessmentQuestionCanvas
      document={draft.document}
      onDocumentChange={updateDocument}
      onImport={() => void openImport()}
      onPreview={() => void showPreview()}
    /> : null}
    {tab === 'settings' ? <main className="assessment-settings">
      <h2>Publish mode</h2>
      <p>Choose how learners enter, what the server stores, and when feedback appears.</p>
      <div className="assessment-mode-grid">
        <label><input type="radio" name="mode" value="practice" checked={mode === 'practice'} onChange={() => { setMode('practice'); setAttempts(1) }} />
          <strong>Practice</strong><span>Anonymous, browser-local, immediate feedback.</span></label>
        <label><input type="radio" name="mode" value="formative" checked={mode === 'formative'} onChange={() => { setMode('formative'); setAttempts(2) }} />
          <strong>Formative</strong><span>Anonymous aggregate or rostered gradebook.</span></label>
        <label><input type="radio" name="mode" value="quiz" checked={mode === 'quiz'} onChange={() => { setMode('quiz'); setAttempts(1) }} />
          <strong>Quiz / Test</strong><span>Roster, ID plus code, deliberate release.</span></label>
      </div>
    </main> : null}
    {tab === 'responses' ? <Suspense fallback={<main className="assessment-main"><p role="status">Loading responses…</p></main>}><AssessmentReportPage embedded /></Suspense> : null}
    {preview ? <div className="assessment-preview-backdrop" onMouseDown={() => setPreview(null)}>
      <div className="assessment-drawer" role="dialog" aria-modal="true" aria-label="Learner preview" onMouseDown={(event) => event.stopPropagation()}>
        <header className="assessment-preview-header"><div className="assessment-preview-header-copy"><span>Assignment preview</span><h2>{preview.title}</h2><p>Review the learner-facing sequence before publishing.</p></div><div className="assessment-preview-header-actions"><button className="assessment-preview-close" type="button" autoFocus aria-label="Close preview" onClick={() => setPreview(null)}><X aria-hidden="true" /></button></div></header>
        <div className="assessment-preview-device-controls" aria-label="Preview size"><button type="button" aria-pressed={previewWidth === 1200} onClick={() => setPreviewWidth(1200)}>Desktop</button><button type="button" aria-pressed={previewWidth === 768} onClick={() => setPreviewWidth(768)}>Tablet</button><button type="button" aria-pressed={previewWidth === 390} onClick={() => setPreviewWidth(390)}>Mobile</button><button type="button" onClick={() => setPreviewSeed((seed) => seed + 1)}>Reset preview</button></div>
        <div className="assessment-preview-stage"><div className="assessment-preview-body" style={{ maxWidth: previewWidth }} aria-label="Assignment preview questions">{assessmentItems(preview).length ? <AssessmentLearnerPreview document={preview} seed={`preview-${previewSeed}`} /> : <div className="assessment-preview-empty"><Eye aria-hidden="true" /><h3>No questions to preview</h3><p>Add a question to see the assignment preview.</p></div>}</div></div>
      </div>
    </div> : null}
    {publishOpen ? <div className="assessment-preview-backdrop" onMouseDown={() => setPublishOpen(false)}>
      <div className="assessment-drawer assessment-builder-drawer" role="dialog" aria-modal="true" aria-label="Publish assessment" onMouseDown={(event) => event.stopPropagation()}>
        <header className="assessment-preview-header"><div className="assessment-preview-header-copy"><span>Publish settings</span><h2>{draft.document.title}</h2><p>Choose the learner mode, timing, and access controls.</p></div><div className="assessment-preview-header-actions"><button className="assessment-preview-close" type="button" autoFocus aria-label="Close publish settings" onClick={() => setPublishOpen(false)}><X aria-hidden="true" /></button></div></header>
        <div className="assessment-builder-drawer-body"><label>Mode<select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}><option value="practice">Practice</option><option value="formative">Formative</option><option value="quiz">Quiz / Test</option></select></label>{mode !== 'practice' ? <label>Class<select value={cohortId} onChange={(event) => setCohortId(event.target.value)}><option value="">Anonymous formative only</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : null}<label>Duration (minutes)<input type="number" min="1" max="240" value={duration / 60} onChange={(event) => setDuration(Number(event.target.value) * 60)} /></label><label>Attempts<input type="number" min="1" max="3" value={attempts} onChange={(event) => setAttempts(Number(event.target.value))} /></label>{mode === 'quiz' ? <label>Access code<input value={accessCode} onChange={(event) => setAccessCode(event.target.value)} /></label> : null}<button className="assessment-primary" type="button" onClick={() => void publish()}>Publish assignment</button>{publishedLink ? <p role="status">Published: <a href={publishedLink}>{publishedLink}</a></p> : null}</div>
      </div>
    </div> : null}
    {importOpen ? <div className="assessment-preview-backdrop" onMouseDown={() => setImportOpen(false)}>
      <div className="assessment-drawer assessment-builder-drawer assessment-import-drawer" role="dialog" aria-modal="true" aria-label="Import questions" onMouseDown={(event) => event.stopPropagation()}>
        <header className="assessment-preview-header"><div className="assessment-preview-header-copy"><span>Question library</span><h2>Import questions</h2><p>Copy questions from another assessment draft into this assignment.</p></div><div className="assessment-preview-header-actions"><button className="assessment-preview-close" type="button" autoFocus aria-label="Close import" onClick={() => setImportOpen(false)}><X aria-hidden="true" /></button></div></header>
        <div className="assessment-builder-drawer-body">{importStatus === 'loading' ? <p role="status">Loading assessment drafts…</p> : null}{importStatus === 'error' ? <div className="assessment-import-state" role="alert"><p>{importMessage}</p><button type="button" onClick={() => void openImport()}>Try again</button></div> : null}{importStatus === 'ready' && sources.length === 0 ? <div className="assessment-import-state"><strong>No source drafts available</strong><p>Create or duplicate another assessment before importing questions.</p></div> : null}{importStatus === 'ready' && sources.length > 0 ? <><label>Source assessment<select value={sourceId} onChange={(event) => { setSourceId(event.target.value); setImportIds(new Set()); setImportQuery('') }}><option value="">Choose a draft</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}</select></label>{sourceId ? <><label>Search question library<input type="search" value={importQuery} onChange={(event) => setImportQuery(event.target.value)} /></label><div className="assessment-import-question-list" aria-label="Questions available to import">{assessmentItems(sources.find((source) => source.id === sourceId)!.document).filter((item) => item.prompt.toLocaleLowerCase().includes(importQuery.trim().toLocaleLowerCase())).map((item) => <label key={item.id}><input type="checkbox" checked={importIds.has(item.id)} onChange={() => setImportIds((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })} /> <span>{item.prompt || 'Untitled question'}</span></label>)}</div></> : <p className="assessment-import-hint">Choose a source to review its questions.</p>}{importMessage ? <p role="alert">{importMessage}</p> : null}<button className="assessment-primary" type="button" disabled={importIds.size === 0 || importSubmitting} onClick={() => void importQuestions()}>{importSubmitting ? 'Importing…' : `Import selected${importIds.size ? ` (${importIds.size})` : ''}`}</button></> : null}</div>
      </div>
    </div> : null}
  </div>
}
