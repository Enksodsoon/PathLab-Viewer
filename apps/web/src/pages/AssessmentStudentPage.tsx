import { BookmarkSimple, CheckCircle, Clock } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getAssessmentMetadata, getPracticeBundle } from '../assessment/api'
import type { AssessmentDocument } from '../assessment/types'
import './assessment.css'

export function AssessmentStudentPage() {
  const { publicId = '' } = useParams()
  const [document, setDocument] = useState<AssessmentDocument | null>(null)
  const [mode, setMode] = useState<'practice' | 'formative' | 'quiz'>('practice')
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [marked, setMarked] = useState(false)

  useEffect(() => {
    void getAssessmentMetadata(publicId).then(async (metadata) => {
      setMode(metadata.mode)
      if (metadata.mode === 'practice') {
        const bundle = await getPracticeBundle(publicId)
        setDocument(bundle.definition)
      } else {
        setDocument(metadata.manifest)
      }
    })
  }, [publicId])

  if (!document) return <main className="assessment-loading"><p role="status">Opening assessment…</p></main>
  const item = document.items[0]

  return <div className="assessment-student">
    <header className="assessment-student-header">
      <div className="assessment-brand"><span aria-hidden="true">▦</span><strong>PathLab</strong><small>Assessment</small></div>
      <div><Clock aria-hidden="true" /> <span>{mode === 'practice' ? 'Practice' : 'Time remaining'}</span></div>
    </header>
    <aside className="assessment-student-nav" aria-label="Question navigator">
      <p>Questions</p>
      {document.items.map((question, index) =>
        <button key={question.id} type="button" aria-current={index === 0 ? 'step' : undefined}>
          {index + 1}
        </button>)}
    </aside>
    <main className="assessment-student-main">
      <p className="assessment-kicker">Question 1 of {document.items.length}</p>
      <h1>{document.title}</h1>
      <section className="assessment-student-question">
        <h2>{item?.prompt}</h2>
        {item?.options?.map((option) => <label key={option.id}>
          <input
            type="radio"
            name={item.id}
            aria-label={option.label}
            checked={answers[item.id] === option.id}
            onChange={() => setAnswers((current) => ({ ...current, [item.id]: option.id }))}
          />
          <span>{option.label}</span>
        </label>)}
        {item?.type === 'diagnostic-field' ? <div className="assessment-slide-placeholder">
          <p>Slide workspace</p>
          <button type="button">Add selection</button>
        </div> : null}
      </section>
      <footer className="assessment-student-actions">
        <button
          type="button"
          aria-pressed={marked}
          onClick={() => setMarked((current) => !current)}
        >
          <BookmarkSimple aria-hidden="true" />
          {marked ? 'Marked for review' : 'Mark for review'}
        </button>
        <button className="assessment-primary" type="button" disabled={!item || !answers[item.id]}>
          <CheckCircle aria-hidden="true" /> Submit assessment
        </button>
      </footer>
    </main>
  </div>
}
