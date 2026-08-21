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
  redeemStudyInvitation,
  reportStudyReadiness,
  submitStudyTask,
  withdrawStudy,
} from '../study/api'
import { studyActionCopy, studyReasonCopy, type StudyLocale } from '../study/copy'
import { appendLocalRecord, clearLocalStudy, verifyCachePersistence } from '../study/localStore'
import { inferTraceSim, prepareTraceSim, reasonForAction, resetTraceSim } from '../study/traceSim'
import type { LocalStudyRecord, StudyAction, StudyReason, StudySession } from '../study/types'
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
  const startedAt = useRef(Date.now())

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
  }, [])

  useEffect(() => {
    void getStudySession().then(restore).catch(() => undefined)
    return () => resetTraceSim()
  }, [restore])

  useEffect(() => {
    localStorage.setItem('pathlab-study-language', locale)
  }, [locale])

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
    return () => viewer.removeHandler('canvas-click', selectPoint)
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
    setBusy(true); setError(''); setFeedback(null); setAiAction(null); setAiReason(null)
    try {
      const result = await submitStudyTask(task.id, answer)
      setFeedback(result)
      const activeMs = Math.max(0, Date.now() - startedAt.current)
      const record: LocalStudyRecord = {
        taskId: task.id,
        completedAt: Date.now(),
        completed: result.status === 'completed',
        features: [
          Number(result.correct), Math.min(activeMs / 60_000, 1), Number(hintCount > 0),
          confidence / 5, Number(sourceOpened), Math.min(activeMs / 60_000, 1),
          0, 0, 0, 0, 0, 0,
        ],
      }
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
      const distinctCompleted = records.filter((item) => item.completed).length
      if (aiOptIn && aiReady && distinctCompleted >= 5) {
        try {
          action = (await inferTraceSim(records)).action
          reason = reasonForAction(action, records)
        } catch {
          setAiReady(false)
          action = result.correct ? 'continue' : 'offer_hint'
          reason = result.correct ? 'CONTINUE_PRACTICE' : 'HINT_SUPPORT'
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
    setSourceOpened(false); setFeedback(null); setAiAction(null); setAiReason(null); setError('')
    startedAt.current = Date.now()
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
        {slide ? <OpenSeadragonViewer tileSource={slide.tileSource} onReady={() => undefined} onViewerAttach={task?.type === 'spatial' ? attachSpatialSelection : undefined} /> : <p>Slide unavailable.</p>}
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
          {aiAction && aiReason ? <div className="study-prompt-reason"><Brain aria-hidden="true" /><div><strong>{studyActionCopy(locale, aiAction)}</strong><button type="button" className="study-why" aria-describedby="study-reason">Why this prompt?</button><p id="study-reason">{studyReasonCopy(locale, aiReason)}</p>{aiOptIn && aiReady ? <small>Experimental local AI trained on simulated learners.</small> : <small>Deterministic faculty-guided suggestion.</small>}</div></div> : null}
          <button type="button" onClick={nextTask}>Next task <ArrowRight aria-hidden="true" /></button>
        </section> : null}
        <aside className="study-ai-panel" aria-label="Optional local AI">
          {session.ai.eligible ? aiReady ? <p><CheckCircle aria-hidden="true" /> Local AI ready. You can disable it at any time.</p> : <button type="button" disabled={busy} onClick={() => void enableAi()}><Brain aria-hidden="true" /> Enable experimental local AI</button> : <p>Faculty-guided deterministic mode. Local AI is unavailable until its release approval is complete.</p>}
          {session.ai.eligible && aiReady ? <button type="button" className="study-link-button" onClick={() => { setAiReady(false); setAiOptIn(false); resetTraceSim() }}>Disable local AI</button> : null}
          {aiOptIn && completedCount < 5 ? <p role="status">Learning your study pattern — {completedCount} of 5 distinct tasks.</p> : null}
        </aside>
        {statusText ? <p role="status">{statusText}</p> : null}{error ? <p role="alert" className="study-error">{error}</p> : null}
      </section>
    </div>
    <footer className="study-footer"><button type="button" onClick={() => void clearDevice()}><Trash aria-hidden="true" /> Clear this device</button><button type="button" onClick={() => void withdraw()} disabled={busy}><SignOut aria-hidden="true" /> Withdraw and delete progress</button></footer>
  </main>
}
