import { BookmarkSimple, Check, CheckCircle, Clock, MagnifyingGlass, UserCircle, WifiSlash } from '@phosphor-icons/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { accessAssessment, AssessmentHttpError, getAssessmentMetadata, getAssessmentResult, getPracticeBundle, restoreAssessmentSession, saveAssessmentResponses, searchAssessmentRoster, startAssessmentAttempt, submitAssessmentAttempt, type AssessmentRosterMatch } from '../assessment/api'
import { enqueueAssessmentResponse, listAssessmentOutbox, removeAssessmentOutbox } from '../assessment/outbox'
import { pruneUnreachableResponses, reachableItems } from '../assessment/learnerRuntime'
import { scorePractice } from '../assessment/practiceScoring'
import { type AssessmentDocument, type AssessmentItem } from '../assessment/types'
import { AssessmentLearnerQuestion } from '../components/assessment/AssessmentLearnerQuestion'
import './assessment.css'

type ResponseMap = Record<string, Record<string, unknown>>
type Result = { status: string; released: boolean; score?: { points: string; maximumPoints: string }; needsGrading?: boolean }
const mutationKey = () => globalThis.crypto?.randomUUID?.() ?? `assessment-${Date.now()}-${Math.random()}`
const sessionKey = (publicId: string) => `pathlab-assessment-session:${publicId}`
const practiceKey = (publicId: string) => `pathlab-assessment-practice:${publicId}`
const responseFor = (item: AssessmentItem, responses: ResponseMap) => responses[item.id] ?? {}

function answered(item: AssessmentItem, responses: ResponseMap) {
  const value = responseFor(item, responses)
  if (item.type === 'information' || item.type === 'section-information') return true
  if (item.type === 'multiple-choice' || item.type === 'dropdown') return Boolean(value.optionId || value.other)
  if (item.type === 'checkboxes') return Array.isArray(value.optionIds) && value.optionIds.length > 0
  if (item.type === 'rating') return Number(value.value) >= 1
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
  const [selectedLearner, setSelectedLearner] = useState<AssessmentRosterMatch | null>(null)
  const [rosterMatches, setRosterMatches] = useState<AssessmentRosterMatch[]>([])
  const [rosterSearching, setRosterSearching] = useState(false)
  const [rosterSearchError, setRosterSearchError] = useState('')
  const [rosterSearchCompleted, setRosterSearchCompleted] = useState('')
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

  useEffect(() => {
    if (selectedLearner || identifier.trim().length < 2 || !accessCode.trim() || mode === 'practice') {
      setRosterMatches([])
      setRosterSearching(false)
      setRosterSearchCompleted('')
      return
    }
    let cancelled = false
    const timer = window.setTimeout(() => {
      setRosterSearching(true)
      setRosterSearchError('')
      void searchAssessmentRoster(publicId, identifier.trim(), accessCode.trim()).then((result) => {
        if (!cancelled) setRosterMatches(result.items)
      }).catch(() => {
        if (!cancelled) {
          setRosterMatches([])
          setRosterSearchError('Check the access code, then search again.')
        }
      }).finally(() => {
        if (!cancelled) {
          setRosterSearching(false)
          setRosterSearchCompleted(identifier.trim())
        }
      })
    }, 250)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [accessCode, identifier, mode, publicId, selectedLearner])

  async function enter(kind: 'anonymous' | 'roster') {
    try {
      if (kind === 'roster' && !selectedLearner) return
      const access = await accessAssessment({ kind, publicId, studentIdentifier: selectedLearner?.identifier, accessCode, takeover })
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
      const unpruned = { ...currentResponses, [item.id]: response }
      const next = document ? pruneUnreachableResponses(document, unpruned) : unpruned
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
    const items = reachableItems(document, responses)
    const missing = items.find((item) => item.required && !answered(item, responses))
    if (missing) { setCurrent(items.indexOf(missing)); setReviewing(false); return }
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

  const items = useMemo(() => document ? reachableItems(document, responses) : [], [document, responses])
  const allAnswered = useMemo(() => items.every((item) => !item.required || answered(item, responses)), [items, responses])
  useEffect(() => {
    if (!attemptId) return
    const reachable = new Set(items.map((item) => item.id))
    void listAssessmentOutbox(attemptId).then((entries) => removeAssessmentOutbox(entries.filter((entry) => !reachable.has(entry.itemId)).map((entry) => entry.id)))
  }, [attemptId, items])
  useEffect(() => setCurrent((index) => Math.min(index, Math.max(items.length - 1, 0))), [items.length])
  if (!document) return <main className="assessment-loading"><p role="status">{status}</p></main>
  if (mode !== 'practice' && !csrf) return <main className="assessment-entry">
    <p className="assessment-kicker">{mode === 'quiz' ? 'Roster access' : 'Assessment access'}</p><h1>{document.title}</h1><p className="assessment-entry-intro">Choose your roster record before beginning. Typed text is never accepted as an identity.</p>
    {mode === 'formative' ? <button type="button" onClick={() => void enter('anonymous')}>Continue anonymously</button> : null}
    <label>Access code<input autoComplete="one-time-code" value={accessCode} onChange={(event) => { setAccessCode(event.target.value); setSelectedLearner(null); setRosterSearchCompleted('') }} /></label>
    <div className="assessment-roster-identity"><label htmlFor="assessment-roster-search">Find your roster record</label><div className="assessment-roster-search"><MagnifyingGlass aria-hidden="true" /><input id="assessment-roster-search" role="combobox" aria-autocomplete="list" aria-expanded={rosterMatches.length > 0} aria-controls="assessment-roster-matches" autoComplete="off" placeholder="Search name, student ID, group, or subgroup" value={identifier} onChange={(event) => { setIdentifier(event.target.value); setSelectedLearner(null); setAccessError(false); setRosterSearchCompleted('') }} />{rosterSearching ? <span>Searching…</span> : null}</div>{rosterMatches.length ? <ul id="assessment-roster-matches" role="listbox" aria-label="Matching roster records">{rosterMatches.map((learner) => <li role="option" aria-selected={selectedLearner?.identifier === learner.identifier} key={learner.identifier}><button type="button" onClick={() => { setSelectedLearner(learner); setIdentifier(learner.displayName ?? learner.studentId); setRosterMatches([]); setRosterSearchError(''); setRosterSearchCompleted('') }}><UserCircle aria-hidden="true" /><span><strong>{learner.displayName ?? 'Unnamed learner'}</strong><small>{[learner.studentId, learner.group, learner.subgroup].filter(Boolean).join(' · ')}</small></span></button></li>)}</ul> : null}{selectedLearner ? <div className="assessment-roster-selected"><Check aria-hidden="true" /><span><strong>{selectedLearner.displayName}</strong><small>{[selectedLearner.studentId, selectedLearner.group, selectedLearner.subgroup].filter(Boolean).join(' · ')}</small></span><button type="button" onClick={() => { setSelectedLearner(null); setIdentifier(''); setRosterSearchCompleted('') }}>Change</button></div> : null}{rosterSearchError ? <p role="alert">{rosterSearchError}</p> : rosterSearchCompleted === identifier.trim() && !rosterMatches.length && !selectedLearner ? <p>No roster record matches that search.</p> : null}</div>
    {accessError ? <div role="alert"><p>Unable to access this assessment.</p><label><input type="checkbox" checked={takeover} onChange={(event) => setTakeover(event.target.checked)} /> Take over my active session on this device</label></div> : null}
    <button className="assessment-primary" type="button" disabled={!selectedLearner} onClick={() => void enter('roster')}>Begin assessment</button>
  </main>
  if (result) return <main className="assessment-result"><CheckCircle aria-hidden="true" /><h1>Assessment submitted</h1>{result.score ? <p className="assessment-result-score">{result.score.points} / {result.score.maximumPoints}</p> : <p>Results will appear after your teacher releases them.</p>}{result.needsGrading ? <p>Some answers are awaiting manual grading.</p> : null}</main>
  if (reviewing) return <main className="assessment-final-review"><h1>Review before submitting</h1><ol>{items.filter((item) => item.type !== 'information' && item.type !== 'section-information').map((item, index) => <li key={item.id}><button type="button" onClick={() => { setCurrent(items.indexOf(item)); setReviewing(false) }}>Question {index + 1}: {answered(item, responses) ? 'Answered' : 'Not answered'}{marked.has(item.id) ? ' · Marked' : ''}</button></li>)}</ol><button type="button" onClick={() => setReviewing(false)}>Back</button><button className="assessment-primary" type="button" disabled={!allAnswered} onClick={() => void submit()}>Submit assessment</button></main>

  const item = items[current]
  const value = responseFor(item, responses)
  return <div className="assessment-student">
    <header className="assessment-student-header"><div className="assessment-brand"><span aria-hidden="true">▦</span><strong>PathLab</strong><small>Assessment</small></div><div aria-live="polite">{online ? <Clock aria-hidden="true" /> : <WifiSlash aria-hidden="true" />} <span>{mode === 'practice' ? status : `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')} · ${status}`}</span></div></header>
    <aside className="assessment-student-nav" aria-label="Question navigator"><p>Questions</p>{items.map((question, index) => <button key={question.id} type="button" aria-current={index === current ? 'step' : undefined} onClick={() => setCurrent(index)}>{index + 1}</button>)}</aside>
    <main className="assessment-student-main"><p className="assessment-kicker">Question {current + 1} of {items.length}</p><h1>{document.title}</h1>
      {item.type === 'diagnostic-field' ? <div className="assessment-mobile-tabs"><button type="button" aria-pressed={mobilePanel === 'slide'} onClick={() => setMobilePanel('slide')}>Slide</button><button type="button" aria-pressed={mobilePanel === 'answer'} onClick={() => setMobilePanel('answer')}>Answer</button></div> : null}
      <AssessmentLearnerQuestion item={item} value={value} assets={assets} mobilePanel={mobilePanel} onChange={(response) => update(item, response)} />
      <footer className="assessment-student-actions"><button type="button" aria-pressed={marked.has(item.id)} onClick={() => setMarked((currentMarked) => { const next = new Set(currentMarked); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })}><BookmarkSimple aria-hidden="true" />{marked.has(item.id) ? 'Marked for review' : 'Mark for review'}</button>{current > 0 ? <button type="button" onClick={() => setCurrent((index) => index - 1)}>Previous</button> : null}{current < items.length - 1 ? <button className="assessment-primary" type="button" onClick={() => setCurrent((index) => index + 1)}>Save & next</button> : <button className="assessment-primary" type="button" disabled={Boolean(item.required) && !answered(item, responses)} onClick={() => setReviewing(true)}><CheckCircle aria-hidden="true" /> Submit assessment</button>}</footer>
    </main>
  </div>
}
