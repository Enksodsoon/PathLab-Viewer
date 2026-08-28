import { Check, Eye, PaperPlaneTilt, X } from '@phosphor-icons/react'
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import {
  getAssessmentDraft,
  importAssessmentQuestions,
  listAssessmentClasses,
  listAssessmentDrafts,
  previewAssessmentDraft,
  publishAssessmentDraft,
  saveAssessmentDraft,
} from '../assessment/api'
import { cacheAssessmentDraft, readCachedAssessmentDraft } from '../assessment/draftCache'
import { AssessmentToolbar } from '../components/assessment/AssessmentChrome'
import { AssessmentQuestionCanvas } from '../components/assessment/AssessmentQuestionCanvas'
import type { AssessmentDocument, AssessmentDraft } from '../assessment/types'
import { questionTypesByType } from '../assessment/questionTypes'
import './assessment.css'

const AssessmentReportPage = lazy(() => import('./AssessmentReportPage').then((module) => ({ default: module.AssessmentReportPage })))

export function AssessmentBuilderPage() {
  const { draftId = '' } = useParams()
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
  const [publishedLink, setPublishedLink] = useState('')
  const [importOpen, setImportOpen] = useState(false)
  const [sources, setSources] = useState<AssessmentDraft[]>([])
  const [sourceId, setSourceId] = useState('')
  const [importIds, setImportIds] = useState<Set<string>>(new Set())
  const [importStatus, setImportStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [importSubmitting, setImportSubmitting] = useState(false)
  const [importMessage, setImportMessage] = useState('')
  const revisionRef = useRef(0)
  const acknowledgedDocumentRef = useRef<AssessmentDocument | null>(null)
  const totalPoints = useMemo(() => draft?.document.items.reduce((total, item) => total + (questionTypesByType[item.type].supportsScoring ? Number(item.points || 0) || 0 : 0), 0) ?? 0, [draft])

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
        <span><strong>{draft.document.items.length}</strong> {draft.document.items.length === 1 ? 'question' : 'questions'}</span>
        <span><strong>{totalPoints}</strong> {totalPoints === 1 ? 'point' : 'points'}</span>
        <span className="assessment-save-state" data-state={saveState === 'All changes saved' ? 'saved' : 'pending'} aria-live="polite"><Check aria-hidden="true" /> {saveState}</span>
      </div>
      <div className="assessment-studio-actions">
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
    {tab === 'questions' ? <AssessmentQuestionCanvas
      document={draft.document}
      onDocumentChange={updateDocument}
      onImport={() => void openImport()}
      onPreview={() => void showPreview()}
    /> : null}
    {/* Retained temporarily as reference while the canvas rollout settles.
    {tab === 'questions' ? <main className="assessment-builder-grid">
      <aside className="assessment-form-outline" aria-label="Form outline">
        <header>
          <div>
            <span className="assessment-kicker">Form outline</span>
            <h2>{draft.document.items.length} {draft.document.items.length === 1 ? 'item' : 'items'}</h2>
          </div>
          <button type="button" aria-label="Import questions" onClick={() => void openImport()}><Copy aria-hidden="true" /></button>
        </header>
        <ol>
          {draft.document.items.map((item, index) => <li key={item.id}>
            <button
              type="button"
              className={item.id === activeItemId ? 'active' : ''}
              aria-current={item.id === activeItemId ? 'true' : undefined}
              onClick={() => setActiveItemId(item.id)}
            >
              <span className="assessment-outline-index">{index + 1}</span>
              <span className="assessment-outline-copy"><strong>{item.prompt || 'Untitled question'}</strong><small>{labels[item.type]}{item.required ? ' · Required' : ''}</small></span>
              <DotsSixVertical aria-hidden="true" />
            </button>
          </li>)}
        </ol>
        <div className="assessment-outline-add">
          <span>Add item</span>
          <div>
            {(Object.entries(labels) as Array<[AssessmentItemType, string]>).map(([type, label]) =>
              <button key={type} type="button" aria-label={`Add ${label.toLowerCase()}`} title={label} onClick={() => addItem(type)}>
                <Plus aria-hidden="true" /><span>{label}</span>
              </button>)}
          </div>
        </div>
      </aside>
      <section className="assessment-question-list" aria-label="Questions">
        {draft.document.items.length === 0 ? <div className="assessment-empty">
          <h2>Add the first question</h2>
          <p>Build a focused sequence, then preview it in the exact learner renderer.</p>
        </div> : null}
        {draft.document.items.filter((item) => item.id === activeItemId).map((item) => {
          const index = draft.document.items.findIndex((candidate) => candidate.id === item.id)
          return <fieldset
          key={item.id}
          className="assessment-question-card assessment-question-card--focused"
          aria-label={`Question ${index + 1}`}
        >
          <legend><span>{index + 1}</span> {labels[item.type]}</legend>
          <label>Prompt
            <textarea value={item.prompt} onChange={(event) => updateDocument((document) => ({
              ...document,
              items: document.items.map((candidate) =>
                candidate.id === item.id ? { ...candidate, prompt: event.target.value } : candidate),
            }))} />
          </label>
          {item.type === 'diagnostic-field' ? <div className="assessment-diagnostic">
            <strong>Diagnostic field</strong>
            <p>Choose a privacy-passed static-DZI slide, then mark accepted points or rectangles.</p>
            <button type="button" onClick={() => void listEligibleAssessmentSlides().then((result) => setSlides(result.items))}>Choose slide</button>
            {slides.length ? <select aria-label="Eligible slide" value={item.slideId ?? ''} onChange={(event) => updateItem(item.id, (current) => ({ ...current, slideId: event.target.value, answerKey: { ...current.answerKey, regions: [] } }))}><option value="">Select a slide</option>{slides.map((slide) => <option key={slide.id} value={slide.id}>{slide.displayName}</option>)}</select> : null}
            {item.slideId && slides.find((slide) => slide.id === item.slideId) ? <AssessmentDiagnosticField
              label="Accepted diagnostic regions"
              tileSource={slides.find((slide) => slide.id === item.slideId)!.tileSource}
              selections={(item.answerKey?.regions as DiagnosticSelection[] | undefined) ?? []}
              multiple
              onCommit={(selection) => updateItem(item.id, (current) => ({ ...current, answerKey: { ...current.answerKey, regions: [...((current.answerKey?.regions as DiagnosticSelection[] | undefined) ?? []), selection] } }))}
              onClear={() => updateItem(item.id, (current) => ({ ...current, answerKey: { ...current.answerKey, regions: [] } }))}
            /> : null}
            <label>Accepted diagnoses<input value={((item.answerKey?.diagnoses as string[] | undefined) ?? []).join(', ')} onChange={(event) => updateItem(item.id, (current) => ({ ...current, answerKey: { ...current.answerKey, diagnoses: event.target.value.split(',').map((value) => value.trim()).filter(Boolean) } }))} /></label>
            <details><summary>Advanced scoring</summary><label>Point tolerance<input type="number" min="0" max="1" step="0.01" value={item.scoring?.pointTolerance ?? 0.03} onChange={(event) => updateItem(item.id, (current) => ({ ...current, scoring: { ...current.scoring, pointTolerance: Number(event.target.value), rectangleIou: current.scoring?.rectangleIou ?? 0.25 } }))} /></label><label>Rectangle IoU<input type="number" min="0" max="1" step="0.05" value={item.scoring?.rectangleIou ?? 0.25} onChange={(event) => updateItem(item.id, (current) => ({ ...current, scoring: { ...current.scoring, pointTolerance: current.scoring?.pointTolerance ?? 0.03, rectangleIou: Number(event.target.value) } }))} /></label></details>
          </div> : null}
          {item.options?.map((option, optionIndex) => <label
            key={option.id}
            className="assessment-option"
          >
            <input type={item.type === 'checkboxes' ? 'checkbox' : 'radio'} name={`key-${item.id}`}
              checked={((item.answerKey?.optionIds as string[] | undefined) ?? []).includes(option.id)}
              onChange={() => updateItem(item.id, (current) => {
                const selected = (current.answerKey?.optionIds as string[] | undefined) ?? []
                const optionIds = current.type === 'checkboxes'
                  ? (selected.includes(option.id) ? selected.filter((id) => id !== option.id) : [...selected, option.id])
                  : [option.id]
                return { ...current, answerKey: { ...current.answerKey, optionIds } }
              })} />
            <input aria-label={`Option ${optionIndex + 1}`} value={option.label} onChange={(event) => updateItem(item.id, (current) => ({ ...current, options: current.options?.map((candidate) => candidate.id === option.id ? { ...candidate, label: event.target.value } : candidate) }))} />
          </label>)}
          {item.options ? <><button type="button" onClick={() => updateItem(item.id, (current) => ({ ...current, options: [...(current.options ?? []), { id: newId(), label: `Option ${(current.options?.length ?? 0) + 1}` }] }))}>Add option</button><label>Paste options<textarea placeholder={'One option per line'} onPaste={(event) => { event.preventDefault(); const labels = event.clipboardData.getData('text').split(/\r?\n/).map((value) => value.trim()).filter(Boolean).slice(0, 10); updateItem(item.id, (current) => ({ ...current, options: labels.map((label) => ({ id: newId(), label })), answerKey: { ...current.answerKey, optionIds: [] } })) }} /></label></> : null}
          {item.type === 'short-answer' ? <label>Accepted answers<input value={((item.answerKey?.variants as string[] | undefined) ?? []).join(', ')} onChange={(event) => updateItem(item.id, (current) => ({ ...current, answerKey: { ...current.answerKey, variants: event.target.value.split(',').map((value) => value.trim()).filter(Boolean) } }))} /></label> : null}
          {item.type === 'checkboxes' ? <label><input type="checkbox" checked={item.scoring?.partialCredit ?? false} onChange={(event) => updateItem(item.id, (current) => ({ ...current, scoring: { ...current.scoring, partialCredit: event.target.checked } }))} /> Bounded partial credit</label> : null}
          {!['information'].includes(item.type) ? <label>Feedback<textarea value={item.feedback?.correct ?? ''} onChange={(event) => updateItem(item.id, (current) => ({ ...current, feedback: { ...current.feedback, correct: event.target.value } }))} /></label> : null}
          <div className="assessment-card-actions">
            <button type="button" aria-label={`Move question ${index + 1} up`} disabled={index === 0} onClick={() => moveItem(index, -1)}><ArrowUp /></button>
            <button type="button" aria-label={`Move question ${index + 1} down`} disabled={index === draft.document.items.length - 1} onClick={() => moveItem(index, 1)}><ArrowDown /></button>
            <button type="button" aria-label={`Duplicate question ${index + 1}`} onClick={() => duplicateItem(item)}><Copy /></button>
            {item.type !== 'information' ? <><label>Required <input type="checkbox" checked={item.required ?? false} onChange={(event) => updateItem(item.id, (current) => ({ ...current, required: event.target.checked }))} /></label><label>Points <input value={item.points ?? '0'} onChange={(event) => updateItem(item.id, (current) => ({ ...current, points: event.target.value }))} inputMode="decimal" /></label></> : null}
            <button type="button" aria-label={`Delete question ${index + 1}`} onClick={() =>
              updateDocument((document) => ({
                ...document,
                items: document.items.filter((candidate) => candidate.id !== item.id),
              }))}><Trash /></button>
          </div>
        </fieldset>})}
      </section>
      <aside className="assessment-add-panel">
        <span className="assessment-kicker">Question settings</span>
        <h2>{activeItem ? 'Focused item' : 'Start building'}</h2>
        {activeItem ? <>
          <p>Use the center canvas for content. Required, points, feedback, scoring, and ordering stay with this question.</p>
          <dl className="assessment-inspector-summary">
            <div><dt>Position</dt><dd>{draft.document.items.findIndex((item) => item.id === activeItem.id) + 1} of {draft.document.items.length}</dd></div>
            <div><dt>Type</dt><dd>{labels[activeItem.type]}</dd></div>
          </dl>
          <div className="assessment-inspector-shortcuts">
            <button type="button" onClick={() => {
              duplicateItem(activeItem)
            }}><Copy aria-hidden="true" /> Duplicate</button>
            <button type="button" onClick={() => void showPreview()}>Preview form</button>
          </div>
        </> : <p>Add a question or information section from the form outline.</p>}
        <details>
          <summary>Authoring tips</summary>
          <ul><li>Keep one learning objective per question.</li><li>Preview before publishing.</li><li>Use sections to reduce learner fatigue.</li></ul>
        </details>
      </aside>
    </main> : null} */}
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
        <div className="assessment-preview-body" aria-label="Assignment preview questions">{preview.items.length ? preview.items.map((item, index) => <section className="assessment-preview-question" key={item.id}><div className="assessment-preview-meta"><span>Question {index + 1}</span><span>{questionTypesByType[item.type].label}</span></div><h3>{item.prompt}</h3>{item.options?.length ? <div className="assessment-preview-options">{item.options.map((option) => <label key={option.id}><input disabled type={item.type === 'checkboxes' ? 'checkbox' : 'radio'} /><span>{option.label}</span></label>)}</div> : <p className="assessment-preview-information">Learner response field</p>}</section>) : <div className="assessment-preview-empty"><Eye aria-hidden="true" /><h3>No questions to preview</h3><p>Add a question to see the assignment preview.</p></div>}</div>
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
        <div className="assessment-builder-drawer-body">{importStatus === 'loading' ? <p role="status">Loading assessment drafts…</p> : null}{importStatus === 'error' ? <div className="assessment-import-state" role="alert"><p>{importMessage}</p><button type="button" onClick={() => void openImport()}>Try again</button></div> : null}{importStatus === 'ready' && sources.length === 0 ? <div className="assessment-import-state"><strong>No source drafts available</strong><p>Create or duplicate another assessment before importing questions.</p></div> : null}{importStatus === 'ready' && sources.length > 0 ? <><label>Source assessment<select value={sourceId} onChange={(event) => { setSourceId(event.target.value); setImportIds(new Set()) }}><option value="">Choose a draft</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}</select></label>{sourceId ? <div className="assessment-import-question-list" aria-label="Questions available to import">{sources.find((source) => source.id === sourceId)?.document.items.map((item) => <label key={item.id}><input type="checkbox" checked={importIds.has(item.id)} onChange={() => setImportIds((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })} /> <span>{item.prompt || 'Untitled question'}</span></label>)}</div> : <p className="assessment-import-hint">Choose a source to review its questions.</p>}{importMessage ? <p role="alert">{importMessage}</p> : null}<button className="assessment-primary" type="button" disabled={importIds.size === 0 || importSubmitting} onClick={() => void importQuestions()}>{importSubmitting ? 'Importing…' : `Import selected${importIds.size ? ` (${importIds.size})` : ''}`}</button></> : null}</div>
      </div>
    </div> : null}
  </div>
}
