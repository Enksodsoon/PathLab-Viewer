import { ClipboardText, GraduationCap, Plus, UsersThree } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { createAssessmentDraft, listAssessmentDrafts } from '../assessment/api'
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
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    void listAssessmentDrafts()
      .then((result) => {
        setDrafts(result.items)
        setState('ready')
      })
      .catch(() => setState('error'))
  }, [])

  async function createNew() {
    const draft = await createAssessmentDraft(emptyDocument.title, emptyDocument)
    navigate(`/admin/assessments/${draft.id}`)
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
        <article><span>Open</span><strong>0</strong></article>
        <article><span>Closed</span><strong>0</strong></article>
        <article><span>Total responses</span><strong>0</strong></article>
      </section>
      <label className="assessment-search">Search assessments
        <input type="search" placeholder="Search by title…" />
      </label>
      {state === 'loading' ? <p role="status">Loading assessments…</p> : null}
      {state === 'error' ? <p role="alert">Assessment is currently unavailable.</p> : null}
      <div className="assessment-table" role="table" aria-label="Assessments">
        <div className="assessment-table-head" role="row">
          <span>Assessment</span><span>Status</span><span>Responses</span><span>Revision</span>
        </div>
        {drafts.map((draft) => <button
          key={draft.id}
          type="button"
          className="assessment-table-row"
          onClick={() => navigate(`/admin/assessments/${draft.id}`)}
        >
          <span><strong>{draft.title}</strong><small>Assessment draft</small></span>
          <span><em>{draft.status}</em></span><span>0</span><span>v{draft.revision}</span>
        </button>)}
      </div>
    </main>
  </div>
}
