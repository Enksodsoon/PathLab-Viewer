import { ArrowRight, Brain, CheckCircle, Globe, ShieldCheck, SignOut, Trash } from '@phosphor-icons/react'
import type OpenSeadragon from 'openseadragon'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError } from '../api'
import { Brand } from '../components/Brand'
import { OpenSeadragonViewer, type ViewerAttachmentCallback } from '../components/OpenSeadragonViewer'
import { ThemeControl } from '../theme/ThemeControl'
import {
  getStudySession,
  getStudyEvidence,
  redeemStudyInvitation,
  reportStudyAiEvent,
  reportStudyReadiness,
  submitStudyTask,
  withdrawStudy,
} from '../study/api'
import { studyActionCopy, studyReasonCopy, type StudyLocale } from '../study/copy'
import { appendLocalRecord, clearLocalStudy, loadLocalStudy, verifyCachePersistence } from '../study/localStore'
import { inferTraceSim, prepareTraceSim, reasonForAction, resetTraceSim } from '../study/traceSim'
import type {
  EvidenceBundle, KnowledgeClaim, KnowledgePack, LocalStudyRecord, StudyAction, StudyReason,
  StudySession,
} from '../study/types'
import './StudyPage.css'

type Feedback = Awaited<ReturnType<typeof submitStudyTask>>

function message(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'STUDY_SUBMISSION_THROTTLED') return 'Please wait before submitting another task.'
    if (error.status === 401 || error.status === 410) return 'This study session is no longer available.'
  }
  return error instanceof Error ? error.message : 'The study action could not be completed.'
}

export function StudyPage() {
  const [locale, setLocale] = useState<StudyLocale>(() => localStorage.getItem('pathlab-study-language') === 'th' ? 'th' : 'en')
  const [session, setSession] = useState<StudySession | null>(null)
  const [invite, setInvite] = useState('')
  const [noticeAccepted, setNoticeAccepted] = useState(false)
  const [taskIndex, setTaskIndex] = useState(0)
  const [selectedOption, setSelectedOption] = useState('')
  const [location, setLocation] = useState<{ x: number; y: number } | null>(null)
  const [confidence, setConfidence] = useState(3)
  const [hintCount, setHintCount] = useState(0)
  const [sourceOpened, setSourceOpened] = useState(false)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [error, setError] = useState('')
  const [statusText, setStatusText] = useState('')
  const [busy, setBusy] = useState(false)
  const [aiOptIn, setAiOptIn] = useState(false)
  const [aiReady, setAiReady] = useState(false)
  const [aiAction, setAiAction] = useState<StudyAction | null>(null)
  const [aiReason, setAiReason] = useState<StudyReason | null>(null)
  const [aiIntervened, setAiIntervened] = useState(false)
  const [evidence, setEvidence] = useState<EvidenceBundle | null>(null)
  const [knowledge, setKnowledge] = useState<KnowledgePack | null>(null)
  const [question, setQuestion] = useState('')
  const [tutorClaims, setTutorClaims] = useState<KnowledgeClaim[]>([])
  const [tutorStatus, setTutorStatus] = useState('')
  const tutorWorker = useRef<Worker | null>(null)
  const startedAt = useRef(Date.now())
  const lastCompletedAt = useRef(0)
  const navigation = useRef({
    panDistance: 0, zoomReversals: 0, revisitCount: 0, zoomDirection: 0,
    lastCenter: null as OpenSeadragon.Point | null, lastZoom: null as number | null, regions: new Set<string>(),
  })

  const task = session?.pack.tasks[taskIndex]
  const slide = session?.pack.slides.find((item) => item.viewerSlideId === task?.slideId)
  const completedCount = useMemo(() => new Set(
    session?.progress.filter((item) => item.status === 'completed').map((item) => item.taskId) ?? [],
  ).size, [session])

  const restore = useCallback((next: StudySession) => {
    setSession(next)
    const firstOpen = next.pack.tasks.findIndex((item) => !next.progress.some(
      (progress) => progress.taskId === item.id && progress.status === 'completed',
    ))
    setTaskIndex(firstOpen >= 0 ? firstOpen : 0)
    setError('')
    void loadLocalStudy(next.course.id).then((stored) => {
      lastCompletedAt.current = Math.max(0, ...stored.records.map((record) => record.completedAt))
    })
  }, [])

  useEffect(() => {
    void getStudySession().then(restore).catch(() => undefined)
    tutorWorker.current = new Worker(new URL('../study/groundedTutor.worker.ts', import.meta.url), { type: 'module' })
    return () => { resetTraceSim(); tutorWorker.current?.terminate(); tutorWorker.current = null }
  }, [restore])

  useEffect(() => {
    localStorage.setItem('pathlab-study-language', locale)
  }, [locale])

  useEffect(() => {
    setEvidence(null); setKnowledge(null); setTutorClaims([]); setQuestion(''); setTutorStatus('')
  }, [session?.pack.schema, slide?.viewerSlideId])

  const askTutor = async () => {
    const allowedClaimIds = feedback?.claimIds ?? []
    if (!knowledge || !allowedClaimIds.length || !question.trim()) return
    setBusy(true); setTutorClaims([]); setTutorStatus('')
    const worker = tutorWorker.current
    if (!worker) { setTutorStatus('Local tutor unavailable. Reviewed feedback and citations remain available.'); return }
    try {
      const requestId = crypto.randomUUID()
      const claimIds = await new Promise<string[]>((resolve, reject) => {
        const timer = window.setTimeout(() => reject(new Error('LOCAL_TUTOR_TIMEOUT')), 5_000)
        worker.onmessage = (event: MessageEvent<{ requestId: string; claimIds: string[] }>) => {
          if (event.data.requestId !== requestId) return
          window.clearTimeout(timer); resolve(event.data.claimIds)
        }
        worker.onerror = () => { window.clearTimeout(timer); reject(new Error('LOCAL_TUTOR_FAILED')) }
        worker.postMessage({ requestId, pack: knowledge, question, allowedClaimIds })
      })
      const selected = claimIds.flatMap((id) => knowledge.claims.filter((claim) => claim.id === id))
      setTutorClaims(selected)
      setTutorStatus(selected.length ? '' : 'No reviewed claim supports this question. The tutor abstained.')
    } catch {
      setTutorStatus('Local tutor unavailable. Reviewed feedback and citations remain available.')
    } finally {
      worker.onmessage = null; worker.onerror = null; setBusy(false)
    }
  }

  const redeem = async (event: FormEvent) => {
    event.preventDefault()
    if (!noticeAccepted) return
    setBusy(true); setError('')
    try { restore(await redeemStudyInvitation(invite.trim())) }
    catch (caught) { setError(message(caught)) }
    finally { setBusy(false) }
  }

  const attachSpatialSelection: ViewerAttachmentCallback = useCallback((viewer: OpenSeadragon.Viewer) => {
    const selectPoint = (event: OpenSeadragon.ViewerEvent & { position?: OpenSeadragon.Point; quick?: boolean }) => {
      if (!event.quick || !event.position) return
      const image = viewer.world.getItemAt(0)
      if (!image) return
      const point = image.viewportToImageCoordinates(viewer.viewport.pointFromPixel(event.position))
      const size = image.getContentSize()
      setLocation({ x: Math.max(0, Math.min(1, point.x / size.x)), y: Math.max(0, Math.min(1, point.y / size.y)) })
    }
    viewer.addHandler('canvas-click', selectPoint)
    const observePan = () => {
      const center = viewer.viewport.getCenter(true)
      const previous = navigation.current.lastCenter
      if (previous) navigation.current.panDistance = Math.min(1, navigation.current.panDistance + center.distanceTo(previous))
      navigation.current.lastCenter = center
      const region = `${Math.round(center.x * 8)}:${Math.round(center.y * 8)}`
      if (navigation.current.regions.has(region)) navigation.current.revisitCount += 1
      navigation.current.regions.add(region)
    }
    const observeZoom = () => {
      const zoom = viewer.viewport.getZoom(true)
      const previous = navigation.current.lastZoom
      if (previous !== null) {
        const direction = Math.sign(zoom - previous)
        if (direction && navigation.current.zoomDirection && direction !== navigation.current.zoomDirection) navigation.current.zoomReversals += 1
        if (direction) navigation.current.zoomDirection = direction
      }
      navigation.current.lastZoom = zoom
    }
    viewer.addHandler('pan', observePan); viewer.addHandler('zoom', observeZoom)
    return () => { viewer.removeHandler('canvas-click', selectPoint); viewer.removeHandler('pan', observePan); viewer.removeHandler('zoom', observeZoom) }
  }, [])

  const enableAi = async () => {
    if (!session?.ai.manifest) return
    setBusy(true); setError(''); setStatusText('Preparing local AI…')
    try {
      if (!await verifyCachePersistence(session.course.id)) throw new Error('LOCAL_CACHE_VERIFY_FAILED')
      await prepareTraceSim(session.ai.manifest)
      setAiOptIn(true); setAiReady(true); setStatusText('Local AI is ready on this device.')
      await reportStudyReadiness('ready')
    } catch (caught) {
      setAiOptIn(false); setAiReady(false); setStatusText('Deterministic study guidance remains available.')
      setError(message(caught)); await reportStudyReadiness('fallback').catch(() => undefined)
    } finally { setBusy(false) }
  }

  const submit = async () => {
    if (!session || !task || session.course.status !== 'active') return
    const answer = task.type === 'multiple-choice'
      ? { selectedOption }
      : location ? { x: location.x, y: location.y } : null
    if (!answer) return
    setBusy(true); setError(''); setFeedback(null); setAiAction(null); setAiReason(null); setAiIntervened(false)
    try {
      const result = await submitStudyTask(task.id, answer)
      setFeedback(result)
      if (result.evidence) {
        void getStudyEvidence(result.evidence.url).then(setEvidence).catch(() => setEvidence(null))
      }
      if (result.claims?.length) {
        setKnowledge({
          schema: 'pathlab.knowledge-pack/1', packId: 'task-scoped-grant', version: '1',
          language: 'en', claims: result.claims, checksum: 'task-scoped',
        })
      }
      const activeMs = Math.max(0, Date.now() - startedAt.current)
      const now = Date.now()
      const gap = lastCompletedAt.current ? Math.min((now - lastCompletedAt.current) / 3_600_000, 1) : 0
      const spatialMissing = result.spatialError === undefined ? 1 : 0
      const record: LocalStudyRecord = {
        taskId: task.id,
        completedAt: now,
        completed: result.status === 'completed',
        features: [
          Number(result.correct), Math.min(activeMs / 60_000, 1), Number(hintCount > 0),
          confidence / 5, Number(sourceOpened), Math.min(activeMs / 60_000, 1),
          gap, navigation.current.panDistance, Math.min(navigation.current.zoomReversals / 10, 1),
          Math.min(navigation.current.revisitCount / 10, 1), result.spatialError ?? 0,
          spatialMissing / 12,
        ],
      }
      if (record.completed) lastCompletedAt.current = now
      const records = await appendLocalRecord(session.course.id, record, session.course.endsAt)
      const progress = session.progress.filter((item) => item.taskId !== task.id)
      progress.push({
        taskId: task.id, status: result.status, latestCorrectness: result.correct,
        attemptCount: result.attemptCount, modelManifestId: null,
        createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
      })
      setSession({ ...session, progress })
      let action: StudyAction = result.correct ? 'continue' : 'offer_hint'
      let reason: StudyReason = result.correct ? 'CONTINUE_PRACTICE' : 'HINT_SUPPORT'
      const distinctCompleted = new Set(records.filter((item) => item.completed).map((item) => item.taskId)).size
      if (aiOptIn && aiReady && distinctCompleted >= 5) {
        try {
          action = suppressAction((await inferTraceSim(records)).action, task, hintCount, session.pack.tasks.length)
          reason = reasonForAction(action, records)
          setAiIntervened(true)
          await reportStudyAiEvent(task.id, action).catch(() => undefined)
        } catch {
          setAiReady(false)
          action = result.correct ? 'continue' : 'offer_hint'
          reason = result.correct ? 'CONTINUE_PRACTICE' : 'HINT_SUPPORT'
          await reportStudyAiEvent(task.id, 'fallback').catch(() => undefined)
        }
      }
      setAiAction(action); setAiReason(reason)
    } catch (caught) { setError(message(caught)) }
    finally { setBusy(false) }
  }

  const nextTask = () => {
    if (!session) return
    setTaskIndex((current) => (current + 1) % session.pack.tasks.length)
    setSelectedOption(''); setLocation(null); setConfidence(3); setHintCount(0)
    setSourceOpened(false); setFeedback(null); setAiAction(null); setAiReason(null); setAiIntervened(false); setError('')
    setTutorClaims([]); setQuestion(''); setTutorStatus('')
    startedAt.current = Date.now()
    navigation.current = { panDistance: 0, zoomReversals: 0, revisitCount: 0, zoomDirection: 0, lastCenter: null, lastZoom: null, regions: new Set() }
  }

  const clearDevice = async () => {
    await clearLocalStudy(session?.course.id)
    resetTraceSim(); setAiReady(false); setAiOptIn(false); setStatusText('Local study data cleared.')
  }

  const withdraw = async () => {
    if (!session) return
    setBusy(true)
    try { await withdrawStudy(); await clearLocalStudy(session.course.id); setSession(null); setInvite(''); setStatusText('') }
    catch (caught) { setError(message(caught)) }
    finally { setBusy(false) }
  }

  if (!session) return <main className="study-entry">
    <header className="study-topbar"><Brand product="Study" /><ThemeControl /></header>
    <section className="study-entry-card" aria-labelledby="study-entry-title">
      <span className="study-eyebrow">PathLab Study Coach</span>
      <h1 id="study-entry-title">Learn from faculty-selected slides</h1>
      <p>PathLab assigns a random course pseudonym. It does not ask for or store your name, email, student number, or roster identity.</p>
      <div className="study-privacy"><ShieldCheck aria-hidden="true" /><p>Answers are scored and discarded. Only task status, correctness, attempt count, model manifest ID, and timestamps are retained for the course retention period.</p></div>
      <form onSubmit={(event) => void redeem(event)}>
        <label htmlFor="study-invite">One-time invitation code</label>
        <input id="study-invite" autoComplete="one-time-code" value={invite} onChange={(event) => setInvite(event.target.value)} />
        <label className="study-consent"><input type="checkbox" checked={noticeAccepted} onChange={(event) => setNoticeAccepted(event.target.checked)} /> I understand the pseudonymous data and withdrawal notice.</label>
        <button type="submit" disabled={!noticeAccepted || invite.trim().length < 20 || busy}>Enter Study Mode <ArrowRight aria-hidden="true" /></button>
      </form>
      {error ? <p role="alert" className="study-error">{error}</p> : null}
    </section>
  </main>

  return <main className="study-shell">
    <header className="study-topbar">
      <Brand product="Study" />
      <div className="study-topbar-actions">
        <button type="button" onClick={() => setLocale((value) => value === 'en' ? 'th' : 'en')}><Globe aria-hidden="true" /> {locale === 'en' ? 'ไทย' : 'English'}</button>
        <ThemeControl />
      </div>
    </header>
    <section className="study-course-heading">
      <div><span className="study-eyebrow">{session.pseudonym}</span><h1>{session.course.title}</h1><p>{session.pack.title}</p></div>
      <div className="study-progress" role="status" aria-live="polite"><strong>{completedCount}</strong><span>of {session.pack.tasks.length} tasks complete</span></div>
    </section>
    {session.course.status === 'preparation' ? <p className="study-preparation" role="status">This course is preparing. Slides and optional local AI can be checked, but answers open after activation.</p> : null}
    <div className="study-workspace">
      <section className="study-slide" aria-label="Teaching slide">
        {slide ? <OpenSeadragonViewer tileSource={slide.tileSource} onReady={() => undefined} onViewerAttach={attachSpatialSelection} /> : <p>Slide unavailable.</p>}
        {task?.type === 'spatial' && location ? <p className="study-location" role="status">Region selected at {location.x.toFixed(3)}, {location.y.toFixed(3)}</p> : null}
      </section>
      <section className="study-task" aria-labelledby="study-task-title">
        <span className="study-eyebrow">Task {taskIndex + 1} of {session.pack.tasks.length}</span>
        <h2 id="study-task-title">{task?.prompt}</h2>
        {task?.type === 'multiple-choice' ? <fieldset><legend>Choose one answer</legend>{task.options?.map((option) => <label key={option} className="study-option"><input type="radio" name="study-answer" value={option} checked={selectedOption === option} onChange={() => setSelectedOption(option)} /> <span>{option}</span></label>)}</fieldset> : <p>Select the most appropriate region directly on the slide.</p>}
        <label htmlFor="study-confidence">Confidence: {confidence} / 5</label>
        <input id="study-confidence" type="range" min="1" max="5" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))} />
        {!feedback ? <div className="study-task-actions">
          <button type="button" className="study-secondary" onClick={() => setHintCount((value) => Math.min(3, value + 1))}>Request faculty hint</button>
          <button type="button" disabled={busy || session.course.status !== 'active' || (task?.type === 'multiple-choice' ? !selectedOption : !location)} onClick={() => void submit()}>Check answer</button>
        </div> : null}
        {hintCount > 0 && task?.hints.slice(0, hintCount).map((hint, index) => <p key={hint} className="study-hint"><strong>Hint {index + 1}:</strong> {hint}</p>)}
        {feedback ? <section className={`study-feedback ${feedback.correct ? 'correct' : 'incorrect'}`} aria-live="polite" aria-atomic="true">
          <h3>{feedback.correct ? 'Correct' : 'Review this task'}</h3><p>{feedback.explanation}</p>
          <ul>{feedback.sources.map((source) => <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer" onClick={() => setSourceOpened(true)}>{source.title}</a></li>)}</ul>
          {evidence ? <section className="study-evidence" aria-labelledby="study-evidence-title">
            <h4 id="study-evidence-title">Reviewed research evidence</h4>
            <p><strong>{(evidence.regions ?? evidence.evidence ?? []).length}</strong> evidence regions · <strong>{evidence.cellAggregates.reduce((sum, item) => sum + item.count, 0)}</strong> described nuclei · uncertainty {Math.round(evidence.qc.uncertainty * 100)}%</p>
            {evidence.ihcDescriptors.map((item) => <p key={`${item.regionId}-${item.marker ?? item.markerId}`}><strong>{(item.marker ?? item.markerId ?? 'IHC').toUpperCase()}</strong> {item.compartment ?? item.analysisMode}: {item.dabAreaFraction === undefined ? 'bounded descriptive measurements' : `DAB area ${Math.round(item.dabAreaFraction * 100)}%`}{item.meanDabOd === undefined ? '' : `, mean OD ${item.meanDabOd.toFixed(2)}`}. {item.calibrationStatus === 'calibrated' ? 'Control-calibrated.' : 'Within-slide relative measurement.'} {item.abstentionReason ? `Limitation: ${item.abstentionReason}. ` : ''}Research estimate only.</p>)}
            {evidence.qc.warnings?.map((warning) => <p key={warning} className="study-hint">QC warning: {warning}</p>)}
            {evidence.qc.abstentionReasons.map((reason) => <p key={reason} className="study-hint">Abstention: {reason}</p>)}
            <small>Signed bundle {evidence.manifestSha256.slice(0, 12)}… · non-diagnostic</small>
          </section> : null}
          {knowledge && feedback.claimIds?.length ? <section className="study-tutor" aria-labelledby="study-tutor-title">
            <h4 id="study-tutor-title">Ask reviewed pathology sources</h4>
            <p>Your question stays in browser memory. Responses can only display reviewed claim cards.</p>
            <label htmlFor="study-tutor-question">Question</label>
            <textarea id="study-tutor-question" maxLength={2000} value={question} onChange={(event) => setQuestion(event.target.value)} />
            <button type="button" disabled={busy || !question.trim()} onClick={() => void askTutor()}>Find grounded answer</button>
            {tutorStatus ? <p role="status">{tutorStatus}</p> : null}
            {tutorClaims.map((claim) => <article key={claim.id} className="study-claim">
              <p>{claim.text}</p><a href={claim.source.url} target="_blank" rel="noreferrer">{claim.source.title}</a>
            </article>)}
          </section> : null}
          {aiAction && aiReason ? <div className="study-prompt-reason"><Brain aria-hidden="true" /><div><strong>{studyActionCopy(locale, aiAction)}</strong><button type="button" className="study-why" aria-describedby="study-reason">Why this prompt?</button><p id="study-reason">{studyReasonCopy(locale, aiReason)}</p>{aiIntervened ? <small>Experimental local AI trained on simulated learners.</small> : <small>Deterministic faculty-guided suggestion.</small>}</div></div> : null}
          <button type="button" onClick={nextTask}>Next task <ArrowRight aria-hidden="true" /></button>
        </section> : null}
        <aside className="study-ai-panel" aria-label="Optional local AI">
          {session.ai.eligible ? aiReady ? <p><CheckCircle aria-hidden="true" /> Local AI ready. You can disable it at any time.</p> : <><p>Closed pilot — unapproved model trained on simulated learners. Inference and study-pattern signals remain on this device.</p><button type="button" disabled={busy} onClick={() => void enableAi()}><Brain aria-hidden="true" /> Enable experimental local AI</button></> : <p>Faculty-guided deterministic mode. Local AI is not assigned to this course.</p>}
          {session.ai.eligible && aiReady ? <button type="button" className="study-link-button" onClick={() => { setAiReady(false); setAiOptIn(false); resetTraceSim() }}>Disable local AI</button> : null}
          {aiOptIn && completedCount < 5 ? <p role="status">Learning your study pattern — {completedCount} of 5 distinct tasks.</p> : null}
        </aside>
        {statusText ? <p role="status">{statusText}</p> : null}{error ? <p role="alert" className="study-error">{error}</p> : null}
      </section>
    </div>
    <footer className="study-footer"><button type="button" onClick={() => void clearDevice()}><Trash aria-hidden="true" /> Clear this device</button><button type="button" onClick={() => void withdraw()} disabled={busy}><SignOut aria-hidden="true" /> Withdraw and delete progress</button></footer>
  </main>
}

function suppressAction(
  action: StudyAction,
  task: NonNullable<StudySession['pack']['tasks'][number]>,
  hintCount: number,
  taskCount: number,
): StudyAction {
  if (action === 'offer_hint' && hintCount >= task.hints.length) return 'continue'
  if (action === 'retrieve' && taskCount < 2) return 'continue'
  return action
}
