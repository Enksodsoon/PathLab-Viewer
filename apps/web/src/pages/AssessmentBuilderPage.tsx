import { ArrowDown, ArrowUp, Check, Copy, DotsSixVertical, Plus, Trash } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  getAssessmentDraft,
  importAssessmentQuestions,
  listAssessmentClasses,
  listAssessmentDrafts,
  listEligibleAssessmentSlides,
  previewAssessmentDraft,
  publishAssessmentDraft,
  saveAssessmentDraft,
} from '../assessment/api'
import { cacheAssessmentDraft, readCachedAssessmentDraft } from '../assessment/draftCache'
import type { AssessmentDocument, AssessmentDraft, AssessmentItem, AssessmentItemType, DiagnosticSelection, EligibleAssessmentSlide } from '../assessment/types'
import { AssessmentDiagnosticField } from '../components/AssessmentDiagnosticField'
import './assessment.css'

const labels: Record<AssessmentItemType, string> = {
  'multiple-choice': 'Multiple choice',
  checkboxes: 'Checkboxes',
  'short-answer': 'Short answer',
  paragraph: 'Paragraph',
  'diagnostic-field': 'Diagnostic field',
  information: 'Section / information',
}

function newId() {
  return globalThis.crypto?.randomUUID?.() ?? `assessment-${Date.now()}-${Math.random()}`
}

export function AssessmentBuilderPage() {
  const { draftId = '' } = useParams()
  const [draft, setDraft] = useState<AssessmentDraft | null>(null)
  const [tab, setTab] = useState<'questions' | 'settings' | 'responses'>('questions')
  const [saveState, setSaveState] = useState('Loading…')
  const [publishOpen, setPublishOpen] = useState(false)
  const [mode, setMode] = useState<'practice' | 'formative' | 'quiz'>('formative')
  const [cohortId, setCohortId] = useState('')
  const [duration, setDuration] = useState(3600)
  const [attempts, setAttempts] = useState(2)
  const [accessCode, setAccessCode] = useState('')
  const [classes, setClasses] = useState<Array<{ id: string; name: string }>>([])
  const [slides, setSlides] = useState<EligibleAssessmentSlide[]>([])
  const [preview, setPreview] = useState<AssessmentDocument | null>(null)
  const [publishedLink, setPublishedLink] = useState('')
  const [importOpen, setImportOpen] = useState(false)
  const [sources, setSources] = useState<AssessmentDraft[]>([])
  const [sourceId, setSourceId] = useState('')
  const [importIds, setImportIds] = useState<Set<string>>(new Set())
  const revisionRef = useRef(0)
  const initialRef = useRef(true)

  useEffect(() => {
    void Promise.all([getAssessmentDraft(draftId), readCachedAssessmentDraft(draftId)])
      .then(([server, cached]) => {
        const selected = cached && cached.revision > server.revision ? cached : server
        revisionRef.current = server.revision
        setDraft(selected)
        setSaveState(cached && cached.revision > server.revision
          ? 'Recovered local edits'
          : 'All changes saved')
      })
      .catch(() => setSaveState('Unable to open draft'))
  }, [draftId])

  useEffect(() => {
    if (!draft) return
    if (initialRef.current) {
      initialRef.current = false
      return
    }
    setSaveState('Saving…')
    void cacheAssessmentDraft(draft)
    const timer = window.setTimeout(() => {
      void saveAssessmentDraft(draft.id, revisionRef.current, draft.document)
        .then((saved) => {
          revisionRef.current = saved.revision
          setDraft(saved)
          void cacheAssessmentDraft(saved)
          setSaveState('All changes saved')
        })
        .catch(() => setSaveState('Conflict — reload or duplicate'))
    }, 750)
    return () => window.clearTimeout(timer)
  }, [draft])

  function updateDocument(update: (document: AssessmentDocument) => AssessmentDocument) {
    setDraft((current) => current ? { ...current, document: update(current.document) } : current)
  }

  function addItem(type: AssessmentItemType) {
    updateDocument((document) => ({
      ...document,
      items: [...document.items, {
        id: newId(),
        type,
        prompt: type === 'information' ? 'Section title' : 'Untitled question',
        ...(type === 'information' ? {} : { points: '1', required: false, answerKey: {} }),
        ...(['multiple-choice', 'checkboxes'].includes(type) ? {
          options: [
            { id: newId(), label: 'Option 1' },
            { id: newId(), label: 'Option 2' },
          ],
        } : {}),
      }],
    }))
  }

  function updateItem(itemId: string, update: (item: AssessmentItem) => AssessmentItem) {
    updateDocument((document) => ({
      ...document,
      items: document.items.map((item) => item.id === itemId ? update(item) : item),
    }))
  }

  function moveItem(index: number, offset: -1 | 1) {
    updateDocument((document) => {
      const destination = index + offset
      if (destination < 0 || destination >= document.items.length) return document
      const items = [...document.items]
      ;[items[index], items[destination]] = [items[destination], items[index]]
      return { ...document, items }
    })
  }

  function duplicateItem(item: AssessmentItem) {
    const optionMap = new Map((item.options ?? []).map((option) => [option.id, newId()]))
    const answerIds = (item.answerKey?.optionIds as string[] | undefined)?.map((id) => optionMap.get(id) ?? id)
    updateDocument((document) => ({ ...document, items: [...document.items, {
      ...structuredClone(item), id: newId(), options: item.options?.map((option) => ({ ...option, id: optionMap.get(option.id)! })),
      answerKey: { ...item.answerKey, ...(answerIds ? { optionIds: answerIds } : {}) },
    }] }))
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
    const result = await listAssessmentDrafts()
    setSources(result.items.filter((item) => item.id !== draft?.id))
    setImportOpen(true)
  }

  async function importQuestions() {
    if (!draft || !sourceId || importIds.size === 0) return
    const saved = await importAssessmentQuestions(draft.id, sourceId, [...importIds], revisionRef.current)
    revisionRef.current = saved.revision
    setDraft(saved); setImportOpen(false); setImportIds(new Set())
  }

  if (!draft) return <main className="assessment-loading"><p role="status">{saveState}</p></main>

  return <div className="assessment-builder">
    <header className="assessment-builder-header">
      <a href="/admin/assessments" aria-label="Back to My Assessments">←</a>
      <div><p>PathLab Assessment</p><h1>{draft.document.title}</h1></div>
      <span className="assessment-save-state"><Check aria-hidden="true" /> {saveState}</span>
      <button type="button" onClick={() => void showPreview()}>Preview</button>
      <button className="assessment-primary" type="button" onClick={openPublish}>Publish</button>
    </header>
    <div className="assessment-tabs" role="tablist" aria-label="Assessment builder">
      {(['questions', 'responses', 'settings'] as const).map((value) =>
        <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)}>
          {value[0].toUpperCase() + value.slice(1)}
        </button>)}
    </div>
    {tab === 'questions' ? <main className="assessment-builder-grid">
      <section className="assessment-question-list" aria-label="Questions">
        {draft.document.items.length === 0 ? <div className="assessment-empty">
          <p className="assessment-kicker">Start with the evidence</p>
          <h2>Add the first question</h2>
          <p>Build a focused sequence, then preview it in the exact learner renderer.</p>
        </div> : null}
        {draft.document.items.map((item, index) => <fieldset
          key={item.id}
          className="assessment-question-card"
          aria-label={`Question ${index + 1}`}
        >
          <legend><DotsSixVertical aria-hidden="true" /> {index + 1}. {labels[item.type]}</legend>
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
        </fieldset>)}
      </section>
      <aside className="assessment-add-panel">
        <h2>Add question</h2>
        <button type="button" onClick={() => void openImport()}><Copy aria-hidden="true" /> Import questions</button>
        {(Object.entries(labels) as Array<[AssessmentItemType, string]>).map(([type, label]) =>
          <button key={type} type="button" aria-label={`Add ${label.toLowerCase()}`}
            onClick={() => addItem(type)}>
            <Plus aria-hidden="true" /> {label}
          </button>)}
      </aside>
    </main> : null}
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
    {tab === 'responses' ? <main className="assessment-settings">
      <h2>Responses</h2>
      <p>Results appear after a published administration receives submissions.</p>
    </main> : null}
    {preview ? <div className="assessment-drawer" role="dialog" aria-modal="true" aria-label="Learner preview"><button type="button" onClick={() => setPreview(null)}>Close preview</button><h2>{preview.title}</h2>{preview.items.map((item) => <section key={item.id}><h3>{item.prompt}</h3>{item.options?.map((option) => <label key={option.id}><input disabled type={item.type === 'checkboxes' ? 'checkbox' : 'radio'} /> {option.label}</label>)}</section>)}</div> : null}
    {publishOpen ? <div className="assessment-drawer" role="dialog" aria-modal="true" aria-label="Publish assessment"><button type="button" onClick={() => setPublishOpen(false)}>Close</button><h2>Publish {draft.document.title}</h2><label>Mode<select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}><option value="practice">Practice</option><option value="formative">Formative</option><option value="quiz">Quiz / Test</option></select></label>{mode !== 'practice' ? <label>Class<select value={cohortId} onChange={(event) => setCohortId(event.target.value)}><option value="">Anonymous formative only</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : null}<label>Duration (minutes)<input type="number" min="1" max="240" value={duration / 60} onChange={(event) => setDuration(Number(event.target.value) * 60)} /></label><label>Attempts<input type="number" min="1" max="3" value={attempts} onChange={(event) => setAttempts(Number(event.target.value))} /></label>{mode === 'quiz' ? <label>Access code<input value={accessCode} onChange={(event) => setAccessCode(event.target.value)} /></label> : null}<button className="assessment-primary" type="button" onClick={() => void publish()}>Publish</button>{publishedLink ? <p role="status">Published: <a href={publishedLink}>{publishedLink}</a></p> : null}</div> : null}
    {importOpen ? <div className="assessment-drawer" role="dialog" aria-modal="true" aria-label="Import questions"><button type="button" onClick={() => setImportOpen(false)}>Close</button><h2>Import questions</h2><label>Source assessment<select value={sourceId} onChange={(event) => { setSourceId(event.target.value); setImportIds(new Set()) }}><option value="">Choose a draft</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}</select></label>{sources.find((source) => source.id === sourceId)?.document.items.map((item) => <label key={item.id}><input type="checkbox" checked={importIds.has(item.id)} onChange={() => setImportIds((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })} /> {item.prompt}</label>)}<button className="assessment-primary" type="button" disabled={importIds.size === 0} onClick={() => void importQuestions()}>Import selected</button></div> : null}
  </div>
}
