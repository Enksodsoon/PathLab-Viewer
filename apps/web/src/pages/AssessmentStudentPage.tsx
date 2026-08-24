import { BookmarkSimple, CheckCircle, Clock, WifiSlash } from '@phosphor-icons/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { accessAssessment, AssessmentHttpError, getAssessmentMetadata, getAssessmentResult, getPracticeBundle, restoreAssessmentSession, saveAssessmentResponses, startAssessmentAttempt, submitAssessmentAttempt } from '../assessment/api'
import { enqueueAssessmentResponse, listAssessmentOutbox, removeAssessmentOutbox } from '../assessment/outbox'
import { scorePractice } from '../assessment/practiceScoring'
import type { AssessmentDocument, AssessmentItem, DiagnosticSelection } from '../assessment/types'
import { AssessmentDiagnosticField } from '../components/AssessmentDiagnosticField'
import './assessment.css'

type ResponseMap = Record<string, Record<string, unknown>>
type Result = { status: string; released: boolean; score?: { points: string; maximumPoints: string }; needsGrading?: boolean }
const mutationKey = () => globalThis.crypto?.randomUUID?.() ?? `assessment-${Date.now()}-${Math.random()}`
const sessionKey = (publicId: string) => `pathlab-assessment-session:${publicId}`
const practiceKey = (publicId: string) => `pathlab-assessment-practice:${publicId}`
const responseFor = (item: AssessmentItem, responses: ResponseMap) => responses[item.id] ?? {}

function answered(item: AssessmentItem, responses: ResponseMap) {
  const value = responseFor(item, responses)
  if (item.type === 'information') return true
  if (item.type === 'multiple-choice') return Boolean(value.optionId)
  if (item.type === 'checkboxes') return Array.isArray(value.optionIds) && value.optionIds.length > 0
  if (item.type === 'diagnostic-field') return Boolean(value.selection || value.diagnosis)
  return Boolean(String(value.text ?? '').trim())
}

export function AssessmentStudentPage() {
  const { publicId = '' } = useParams()
  const [document, setDocument] = useState<AssessmentDocument | null>(null)
  const [assets, setAssets] = useState<Record<string, string>>({})
  const [mode, setMode] = useState<'practice' | 'formative' | 'quiz'>('practice')
  const [status, setStatus] = useState('Opening assessment…')
  const [csrf, setCsrf] = useState(() => sessionStorage.getItem(sessionKey(publicId)) ?? '')
  const [attemptId, setAttemptId] = useState('')
  const [responses, setResponses] = useState<ResponseMap>({})
  const [revisions, setRevisions] = useState<Record<string, number>>({})
  const [marked, setMarked] = useState<Set<string>>(new Set())
  const [current, setCurrent] = useState(0)
  const [reviewing, setReviewing] = useState(false)
  const [result, setResult] = useState<Result | null>(null)
  const [identifier, setIdentifier] = useState('')
  const [accessCode, setAccessCode] = useState('')
  const [accessError, setAccessError] = useState(false)
  const [takeover, setTakeover] = useState(false)
  const [online, setOnline] = useState(navigator.onLine)
  const [mobilePanel, setMobilePanel] = useState<'slide' | 'answer'>('slide')
  const [duration, setDuration] = useState(0)
  const [startedAt, setStartedAt] = useState('')
  const [remaining, setRemaining] = useState(0)
  const [practiceExpiry, setPracticeExpiry] = useState(() => Date.now() + 30 * 24 * 60 * 60 * 1000)
  const syncTimer = useRef<number | null>(null)

  const restore = useCallback(async (token: string) => {
    const session = await restoreAssessmentSession(token)
    setDocument(session.manifest)
    if (session.attempt) {
      setAttemptId(session.attempt.id)
      setResponses(Object.fromEntries(session.attempt.responses.map((entry) => [entry.itemId, entry.response])))
      setRevisions(Object.fromEntries(session.attempt.responses.map((entry) => [entry.itemId, entry.revision])))
      setStartedAt(session.attempt.startedAt)
    }
    setStatus('Saved')
  }, [])

  useEffect(() => {
    let cancelled = false
    void getAssessmentMetadata(publicId).then(async (metadata) => {
      if (cancelled) return
      setMode(metadata.mode)
      setDuration(metadata.durationSeconds)
      setPracticeExpiry(Math.min(
        Date.now() + 30 * 24 * 60 * 60 * 1000,
        metadata.closesAt ? new Date(metadata.closesAt).getTime() + 24 * 60 * 60 * 1000 : Number.POSITIVE_INFINITY,
      ))
      setAssets(metadata.assets ?? {})
      if (metadata.mode === 'practice') {
        const bundle = await getPracticeBundle(publicId)
        if (cancelled) return
        setDocument(bundle.definition)
        setAssets(bundle.assets ?? {})
        const cached = localStorage.getItem(practiceKey(publicId))
        if (cached) {
          const parsed = JSON.parse(cached) as { expiresAt: number; responses: ResponseMap }
          if (parsed.expiresAt > Date.now()) setResponses(parsed.responses)
        }
        setStatus('Stored only in this browser')
      } else if (csrf) {
        await restore(csrf).catch(() => {
          sessionStorage.removeItem(sessionKey(publicId))
          setCsrf('')
          setDocument(metadata.manifest)
        })
      } else {
        setDocument(metadata.manifest)
        setStatus('Sign in to begin')
      }
    }).catch(() => setStatus('Assessment unavailable'))
    return () => { cancelled = true }
  }, [csrf, publicId, restore])

  useEffect(() => {
    if (!startedAt || mode === 'practice') return
    const updateClock = () => setRemaining(Math.max(0, duration - Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)))
    updateClock()
    const timer = window.setInterval(updateClock, 1000)
    return () => window.clearInterval(timer)
  }, [duration, mode, startedAt])

  const syncOutbox = useCallback(async () => {
    if (!attemptId || !csrf || !navigator.onLine) return
    const pending = await listAssessmentOutbox(attemptId)
    const latestPending = new Map<string, typeof pending[number]>()
    pending.forEach((entry) => {
      const current = latestPending.get(entry.itemId)
      if (!current || entry.revision > current.revision) latestPending.set(entry.itemId, entry)
    })
    if (latestPending.size) {
      setResponses((currentResponses) => ({ ...currentResponses, ...Object.fromEntries([...latestPending].map(([itemId, entry]) => [itemId, entry.response])) }))
      setRevisions((currentRevisions) => ({ ...currentRevisions, ...Object.fromEntries([...latestPending].map(([itemId, entry]) => [itemId, entry.revision])) }))
    }
    for (let index = 0; index < pending.length; index += 10) {
      const batch = pending.slice(index, index + 10)
      try {
        await saveAssessmentResponses(attemptId, csrf, mutationKey(), batch.map(({ itemId, revision, response }) => ({ itemId, revision, response })))
        await removeAssessmentOutbox(batch.map((entry) => entry.id))
      } catch (error) {
        if (!(error instanceof AssessmentHttpError) || error.detail.code !== 'ASSESSMENT_RESPONSE_CONFLICT') throw error
        const authoritative = error.detail.authoritative as Array<{ itemId: string; revision: number; response: Record<string, unknown> }>
        setResponses((currentResponses) => ({ ...currentResponses, ...Object.fromEntries(authoritative.map((entry) => [entry.itemId, entry.response])) }))
        setRevisions((currentRevisions) => ({ ...currentRevisions, ...Object.fromEntries(authoritative.map((entry) => [entry.itemId, entry.revision])) }))
        await removeAssessmentOutbox(batch.filter((entry) => authoritative.some((server) => server.itemId === entry.itemId)).map((entry) => entry.id))
        setStatus('Conflict — server response restored')
        return
      }
    }
    setStatus('Saved')
  }, [attemptId, csrf])

  useEffect(() => {
    const connected = () => { setOnline(true); void syncOutbox() }
    const disconnected = () => setOnline(false)
    window.addEventListener('online', connected)
    window.addEventListener('offline', disconnected)
    return () => { window.removeEventListener('online', connected); window.removeEventListener('offline', disconnected) }
  }, [syncOutbox])

  useEffect(() => {
    void syncOutbox().catch(() => setStatus('Saved locally — retrying'))
  }, [syncOutbox])

  useEffect(() => () => {
    if (syncTimer.current !== null) window.clearTimeout(syncTimer.current)
  }, [])

  async function enter(kind: 'anonymous' | 'roster') {
    try {
      const access = await accessAssessment({ kind, publicId, studentIdentifier: identifier, accessCode, takeover })
      sessionStorage.setItem(sessionKey(publicId), access.csrfToken)
      setCsrf(access.csrfToken)
      setAccessError(false)
      const attempt = await startAssessmentAttempt(access.csrfToken, mutationKey())
      setAttemptId(attempt.id)
      setStartedAt(attempt.startedAt)
      setStatus('Saved')
      await restore(access.csrfToken)
    } catch { setAccessError(true) }
  }

  function update(item: AssessmentItem, response: Record<string, unknown>) {
    setResponses((currentResponses) => {
      const next = { ...currentResponses, [item.id]: response }
      if (mode === 'practice') localStorage.setItem(practiceKey(publicId), JSON.stringify({ responses: next, expiresAt: practiceExpiry }))
      return next
    })
    if (mode !== 'practice' && attemptId) {
      const revision = (revisions[item.id] ?? 0) + 1
      setRevisions((currentRevisions) => ({ ...currentRevisions, [item.id]: revision }))
      setStatus(navigator.onLine ? 'Saving…' : 'Offline — queued')
      void enqueueAssessmentResponse({ id: `${attemptId}:${item.id}:${revision}`, publicId, attemptId, itemId: item.id, revision, response, createdAt: Date.now() }).then(() => {
        if (syncTimer.current !== null) window.clearTimeout(syncTimer.current)
        syncTimer.current = window.setTimeout(() => { void syncOutbox() }, 750)
      })
    }
  }

  async function submit() {
    if (!document) return
    const missing = document.items.find((item) => item.required && !answered(item, responses))
    if (missing) { setCurrent(document.items.indexOf(missing)); setReviewing(false); return }
    if (mode === 'practice') {
      const score = scorePractice(document, responses)
      setResult({ status: 'submitted', released: true, score: { points: String(score.points), maximumPoints: String(score.maximumPoints) }, needsGrading: Object.values(score.breakdown).some((value) => value === null) })
      return
    }
    await syncOutbox()
    const submitted = await submitAssessmentAttempt(attemptId, csrf, mutationKey())
    const released = await getAssessmentResult(attemptId, csrf).catch(() => ({ ...submitted, released: false }))
    setResult({ ...released, needsGrading: submitted.needsGrading })
  }

  const allAnswered = useMemo(() => document?.items.every((item) => !item.required || answered(item, responses)) ?? false, [document, responses])
  if (!document) return <main className="assessment-loading"><p role="status">{status}</p></main>
  if (mode !== 'practice' && !csrf) return <main className="assessment-entry">
    <p className="assessment-kicker">{mode === 'quiz' ? 'Roster access' : 'Assessment access'}</p><h1>{document.title}</h1>
    {mode === 'formative' ? <button type="button" onClick={() => void enter('anonymous')}>Continue anonymously</button> : null}
    <label>Student identifier<input value={identifier} onChange={(event) => setIdentifier(event.target.value)} /></label>
    <label>Access code<input value={accessCode} onChange={(event) => setAccessCode(event.target.value)} /></label>
    {accessError ? <div role="alert"><p>Unable to access this assessment.</p><label><input type="checkbox" checked={takeover} onChange={(event) => setTakeover(event.target.checked)} /> Take over my active session on this device</label></div> : null}
    <button className="assessment-primary" type="button" onClick={() => void enter('roster')}>Begin assessment</button>
  </main>
  if (result) return <main className="assessment-result"><CheckCircle aria-hidden="true" /><h1>Assessment submitted</h1>{result.score ? <p className="assessment-result-score">{result.score.points} / {result.score.maximumPoints}</p> : <p>Results will appear after your teacher releases them.</p>}{result.needsGrading ? <p>Some answers are awaiting manual grading.</p> : null}</main>
  if (reviewing) return <main className="assessment-final-review"><h1>Review before submitting</h1><ol>{document.items.filter((item) => item.type !== 'information').map((item, index) => <li key={item.id}><button type="button" onClick={() => { setCurrent(document.items.indexOf(item)); setReviewing(false) }}>Question {index + 1}: {answered(item, responses) ? 'Answered' : 'Not answered'}{marked.has(item.id) ? ' · Marked' : ''}</button></li>)}</ol><button type="button" onClick={() => setReviewing(false)}>Back</button><button className="assessment-primary" type="button" disabled={!allAnswered} onClick={() => void submit()}>Submit assessment</button></main>

  const item = document.items[current]
  const value = responseFor(item, responses)
  const diagnosticSelections = value.selection ? [value.selection as DiagnosticSelection] : []
  const tileSource = item.slideId ? assets[item.slideId] : undefined
  return <div className="assessment-student">
    <header className="assessment-student-header"><div className="assessment-brand"><span aria-hidden="true">▦</span><strong>PathLab</strong><small>Assessment</small></div><div aria-live="polite">{online ? <Clock aria-hidden="true" /> : <WifiSlash aria-hidden="true" />} <span>{mode === 'practice' ? status : `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')} · ${status}`}</span></div></header>
    <aside className="assessment-student-nav" aria-label="Question navigator"><p>Questions</p>{document.items.map((question, index) => <button key={question.id} type="button" aria-current={index === current ? 'step' : undefined} onClick={() => setCurrent(index)}>{index + 1}</button>)}</aside>
    <main className="assessment-student-main"><p className="assessment-kicker">Question {current + 1} of {document.items.length}</p><h1>{document.title}</h1>
      {item.type === 'diagnostic-field' ? <div className="assessment-mobile-tabs"><button type="button" aria-pressed={mobilePanel === 'slide'} onClick={() => setMobilePanel('slide')}>Slide</button><button type="button" aria-pressed={mobilePanel === 'answer'} onClick={() => setMobilePanel('answer')}>Answer</button></div> : null}
      <section className="assessment-student-question"><h2>{item.prompt}</h2>
        {item.options?.map((option) => {
          const selected = (value.optionIds as string[] | undefined) ?? []
          return <label key={option.id}><input type={item.type === 'checkboxes' ? 'checkbox' : 'radio'} name={item.id} aria-label={option.label} checked={item.type === 'checkboxes' ? selected.includes(option.id) : value.optionId === option.id} onChange={() => item.type === 'checkboxes' ? update(item, { optionIds: selected.includes(option.id) ? selected.filter((id) => id !== option.id) : [...selected, option.id] }) : update(item, { optionId: option.id })} /><span>{option.label}</span></label>
        })}
        {['short-answer', 'paragraph'].includes(item.type) ? <textarea aria-label="Answer" value={String(value.text ?? '')} onChange={(event) => update(item, { text: event.target.value })} /> : null}
        {item.type === 'diagnostic-field' && tileSource ? <div className="assessment-slide-panel" data-active={mobilePanel === 'slide'}><AssessmentDiagnosticField label="Diagnostic slide" tileSource={tileSource} selections={diagnosticSelections} onCommit={(selection) => update(item, { ...value, selection })} onClear={() => update(item, { ...value, selection: undefined })} /></div> : null}
        {item.type === 'diagnostic-field' ? <div className="assessment-answer-panel" data-active={mobilePanel === 'answer'}><label>Diagnosis<input value={String(value.diagnosis ?? '')} onChange={(event) => update(item, { ...value, diagnosis: event.target.value })} /></label></div> : null}
      </section>
      <footer className="assessment-student-actions"><button type="button" aria-pressed={marked.has(item.id)} onClick={() => setMarked((currentMarked) => { const next = new Set(currentMarked); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })}><BookmarkSimple aria-hidden="true" />{marked.has(item.id) ? 'Marked for review' : 'Mark for review'}</button>{current > 0 ? <button type="button" onClick={() => setCurrent((index) => index - 1)}>Previous</button> : null}{current < document.items.length - 1 ? <button className="assessment-primary" type="button" onClick={() => setCurrent((index) => index + 1)}>Save & next</button> : <button className="assessment-primary" type="button" disabled={Boolean(item.required) && !answered(item, responses)} onClick={() => setReviewing(true)}><CheckCircle aria-hidden="true" /> Submit assessment</button>}</footer>
    </main>
  </div>
}
