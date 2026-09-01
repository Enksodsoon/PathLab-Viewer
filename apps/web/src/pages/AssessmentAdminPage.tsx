import { ClipboardText, GraduationCap, Plus, UsersThree } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { archiveAssessmentDraft, createAssessmentDraft, duplicateAssessmentDraft, listAssessmentAdministrations, listAssessmentDrafts, type AssessmentAdministrationSummary } from '../assessment/api'
import type { AssessmentDraft } from '../assessment/types'
import './assessment.css'

const emptyDocument = {
  title: 'Untitled assessment',
  items: [],
  settings: { mode: 'formative' as const, shuffleQuestions: false },
}

export function AssessmentAdminPage() {
  const navigate = useNavigate()
  const [drafts, setDrafts] = useState<AssessmentDraft[]>([])
  const [administrations, setAdministrations] = useState<AssessmentAdministrationSummary[]>([])
  const [query, setQuery] = useState('')
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    void Promise.all([listAssessmentDrafts(), listAssessmentAdministrations()])
      .then(([draftResult, administrationResult]) => {
        setDrafts(draftResult.items)
        setAdministrations(administrationResult.items)
        setState('ready')
      })
      .catch(() => setState('error'))
  }, [])

  async function createNew() {
    const draft = await createAssessmentDraft(emptyDocument.title, emptyDocument)
    navigate(`/admin/assessments/${draft.id}`)
  }

  async function duplicate(id: string) {
    const created = await duplicateAssessmentDraft(id)
    setDrafts((current) => [created, ...current])
  }

  async function archive(id: string) {
    const updated = await archiveAssessmentDraft(id)
    setDrafts((current) => current.map((item) => item.id === id ? updated : item))
  }

  return <div className="assessment-shell">
    <aside className="assessment-rail" aria-label="Assessment navigation">
      <div className="assessment-brand"><span aria-hidden="true">▦</span><strong>PathLab</strong><small>Assessment</small></div>
      <nav>
        <a className="active" href="/admin/assessments"><ClipboardText /> My Assessments</a>
        <a href="/admin/assessments/classes"><UsersThree /> Classes</a>
        <a href="/admin/assessments/results"><GraduationCap /> Results</a>
      </nav>
      <a className="assessment-back" href="/admin">← Slide library</a>
    </aside>
    <main className="assessment-main">
      <header className="assessment-page-header">
        <div><p className="assessment-kicker">Authoring workspace</p><h1>My Assessments</h1></div>
        <button className="assessment-primary" type="button" onClick={() => void createNew()}>
          <Plus aria-hidden="true" /> New assessment
        </button>
      </header>
      <section className="assessment-metrics" aria-label="Assessment status">
        <article><span>Drafts</span><strong>{drafts.filter((item) => item.status === 'draft').length}</strong></article>
        <article><span>Open</span><strong>{administrations.filter((item) => item.status === 'open').length}</strong></article>
        <article><span>Closed</span><strong>{administrations.filter((item) => item.status === 'closed').length}</strong></article>
        <article><span>Total responses</span><strong>{administrations.reduce((total, item) => total + item.responses, 0)}</strong></article>
      </section>
      <label className="assessment-search">Search assessments
        <input type="search" placeholder="Search by title…" value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>
      {state === 'loading' ? <p role="status">Loading assessments…</p> : null}
      {state === 'error' ? <p role="alert">Assessment is currently unavailable.</p> : null}
      <div className="assessment-table" role="table" aria-label="Assessments">
        <div className="assessment-table-head" role="row">
          <span>Assessment</span><span>Status</span><span>Reuse</span><span>Archive</span>
        </div>
        {drafts.filter((draft) => draft.title.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())).map((draft) => <div
          key={draft.id}
          className="assessment-table-row"
        >
          <span><button type="button" onClick={() => navigate(`/admin/assessments/${draft.id}`)}><strong>{draft.title}</strong></button><small>Assessment draft</small></span>
          <span><em>{draft.status}</em></span><span><button type="button" onClick={() => void duplicate(draft.id)}>Duplicate</button></span><span><button type="button" onClick={() => void archive(draft.id)} disabled={draft.status === 'archived'}>Archive</button></span>
        </div>)}
      </div>
    </main>
  </div>
}
