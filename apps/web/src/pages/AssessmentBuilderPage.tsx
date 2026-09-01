import { Check, DotsSixVertical, Plus, Trash } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  getAssessmentDraft,
  previewAssessmentDraft,
  publishAssessmentDraft,
  saveAssessmentDraft,
} from '../assessment/api'
import { cacheAssessmentDraft, readCachedAssessmentDraft } from '../assessment/draftCache'
import type { AssessmentDocument, AssessmentDraft, AssessmentItemType } from '../assessment/types'
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

  if (!draft) return <main className="assessment-loading"><p role="status">{saveState}</p></main>

  return <div className="assessment-builder">
    <header className="assessment-builder-header">
      <a href="/admin/assessments" aria-label="Back to My Assessments">←</a>
      <div><p>PathLab Assessment</p><h1>{draft.document.title}</h1></div>
      <span className="assessment-save-state"><Check aria-hidden="true" /> {saveState}</span>
      <button type="button" onClick={() => void previewAssessmentDraft(draft.id)}>Preview</button>
      <button className="assessment-primary" type="button"
        onClick={() => void publishAssessmentDraft(draft.id)}>Publish</button>
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
            <button type="button">Choose slide</button>
          </div> : null}
          {item.options?.map((option, optionIndex) => <label
            key={option.id}
            className="assessment-option"
          >
            <input type={item.type === 'checkboxes' ? 'checkbox' : 'radio'}
              name={`key-${item.id}`} />
            <input aria-label={`Option ${optionIndex + 1}`} value={option.label} readOnly />
          </label>)}
          <div className="assessment-card-actions">
            <label>Points <input value={item.points ?? '0'} readOnly inputMode="decimal" /></label>
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
        <label><input type="radio" name="mode" value="practice" />
          <strong>Practice</strong><span>Anonymous, browser-local, immediate feedback.</span></label>
        <label><input type="radio" name="mode" value="formative" defaultChecked />
          <strong>Formative</strong><span>Anonymous aggregate or rostered gradebook.</span></label>
        <label><input type="radio" name="mode" value="quiz" />
          <strong>Quiz / Test</strong><span>Roster, ID plus code, deliberate release.</span></label>
      </div>
    </main> : null}
    {tab === 'responses' ? <main className="assessment-settings">
      <h2>Responses</h2>
      <p>Results appear after a published administration receives submissions.</p>
    </main> : null}
  </div>
}
