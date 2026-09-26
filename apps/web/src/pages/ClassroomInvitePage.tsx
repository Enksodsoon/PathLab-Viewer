import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../api'
import {
  classroomInvitePhase,
  classroomInviteState,
  joinLiveClassroom,
  unlockClassroomInvite,
  type ClassroomInviteState,
} from '../classroom/api'
import { ClassroomSlideNavigator } from '../classroom/ClassroomSlideNavigator'
import { classroomSlideSource } from '../classroom/slideSource'
import { Brand } from '../components/Brand'
import { OpenSeadragonViewer } from '../components/OpenSeadragonViewer'
import { ThemeControl } from '../theme/ThemeControl'
import { CLASSROOM_VIEWER_NETWORK_PROFILE } from '../viewerNetwork'
import '../classroom/classroom.css'

export function ClassroomInvitePage() {
  const { publicId = '' } = useParams()
  const navigate = useNavigate()
  const [accessCode, setAccessCode] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [invite, setInvite] = useState<ClassroomInviteState | null>(null)
  const [slideId, setSlideId] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const generationRef = useRef(0)
  const loadRequestRef = useRef(0)
  const hasInvite = invite !== null

  const load = useCallback(async () => {
    const generation = generationRef.current
    const request = ++loadRequestRef.current
    const next = await classroomInviteState(publicId)
    if (generation !== generationRef.current || request !== loadRequestRef.current) return
    setInvite(next)
    setSlideId((current) => next.slides.some((slide) => slide.id === current) ? current : next.slides[0]?.id || '')
  }, [publicId])

  useEffect(() => {
    generationRef.current += 1
    setInvite(null)
    setSlideId('')
    setMessage('')
    setBusy(false)
    void load().catch(() => undefined)
    return () => { generationRef.current += 1 }
  }, [load])

  useEffect(() => {
    if (!hasInvite) return
    const generation = generationRef.current
    let cancelled = false
    let inFlight = false
    const check = async () => {
      if (document.visibilityState !== 'visible' || inFlight || cancelled) return
      inFlight = true
      try {
        const next = await classroomInvitePhase(publicId)
        if (cancelled || generation !== generationRef.current) return
        setInvite((current) => current ? { ...current, phase: next.phase } : current)
        setMessage((current) => current.startsWith('Review status could not be refreshed') ? '' : current)
      } catch (caught) {
        if (cancelled || generation !== generationRef.current) return
        if (caught instanceof ApiError && (caught.status === 404 || caught.status === 410)) {
          setInvite(null)
          setMessage('This classroom invitation is no longer available.')
        } else {
          setMessage('Review status could not be refreshed. Your slides remain available; retrying automatically.')
        }
      } finally { inFlight = false }
    }
    const timer = window.setInterval(() => void check(), 15_000)
    document.addEventListener('visibilitychange', check)
    return () => {
      cancelled = true
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', check)
    }
  }, [hasInvite, publicId])

  const unlock = async () => {
    const generation = generationRef.current
    setBusy(true)
    setMessage('')
    try {
      await unlockClassroomInvite(publicId, accessCode, displayName)
      if (generation !== generationRef.current) return
      await load()
    } catch (caught) {
      if (generation !== generationRef.current) return
      setMessage(caught instanceof ApiError && caught.status === 429
        ? 'Too many attempts. Wait a few minutes and try again.'
        : 'The invitation or access code is unavailable.')
    } finally { if (generation === generationRef.current) setBusy(false) }
  }

  if (!invite) return <main className="classroom-entry classroom-join">
    <header className="classroom-entry__header"><Brand variant="library" /><ThemeControl compact /></header>
    <section className="classroom-entry__card">
      <p className="classroom-kicker">Protected classroom review</p>
      <h1>Open teaching slides</h1>
      <p className="classroom-entry__intro">Enter the separate access code provided by your teacher.</p>
      <label>Access code<input autoFocus autoComplete="one-time-code" value={accessCode} onChange={(event) => setAccessCode(event.target.value.toUpperCase())} /></label>
      <label>Name (optional)<input autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label>
      <button className="primary classroom-entry__primary" type="button" disabled={busy || accessCode.length < 6} onClick={() => void unlock()}>{busy ? 'Opening…' : 'Open slide review'}</button>
      {message ? <p className="classroom-message" role="status">{message}</p> : null}
    </section>
  </main>

  const slide = invite.slides.find((item) => item.id === slideId) ?? invite.slides[0]
  return <div className="classroom-shell classroom-shell--review">
    <header className="classroom-topbar">
      <Brand variant="library" />
      <div className="classroom-review-status">
        <strong>{invite.phase === 'live' ? 'Class is live' : invite.phase === 'review' ? 'Post-class review' : 'Pre-class review'}</strong>
        <span>Review access ends {new Date(invite.reviewExpiresAt).toLocaleString()}</span>
      </div>
      <div className="classroom-topbar__actions">
        {invite.phase === 'live' ? <button className="primary" type="button" onClick={() => void joinLiveClassroom(invite.sessionId, invite.csrfToken).then(() => navigate(`/classroom/${invite.sessionId}`, { replace: true })).catch(() => setMessage('The live class could not be joined.'))}>Join live class</button> : null}
        <ThemeControl compact />
      </div>
    </header>
    <main className="classroom-viewer">
      {slide ? <OpenSeadragonViewer
        tileSource={classroomSlideSource(slide.tileSource, invite.sessionId)}
        onReady={() => undefined}
        networkProfile={CLASSROOM_VIEWER_NETWORK_PROFILE}
      /> : null}
      <ClassroomSlideNavigator activeId={slide?.id ?? ''} slides={invite.slides} onSelect={setSlideId} />
    </main>
    <aside className="classroom-panel classroom-review-panel">
      <h2>Independent slide review</h2>
      <p>Navigate and zoom freely. Questions, pins, and teacher guidance become available only after you join the live class.</p>
      <strong>{invite.participant.alias}</strong>
      {message ? <p role="status" className="classroom-message">{message}</p> : null}
    </aside>
  </div>
}
