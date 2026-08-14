import { useCallback, useEffect, useState } from 'react'
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

  const load = useCallback(async () => {
    const next = await classroomInviteState(publicId)
    setInvite(next)
    setSlideId((current) => current || next.slides[0]?.id || '')
  }, [publicId])

  useEffect(() => {
    void load().catch(() => undefined)
  }, [load])

  useEffect(() => {
    if (!invite) return
    let timer = 0
    const check = async () => {
      if (document.visibilityState !== 'visible') return
      try {
        const next = await classroomInvitePhase(publicId)
        setInvite((current) => current ? { ...current, phase: next.phase } : current)
      } catch {
        setInvite(null)
        setMessage('This classroom invitation is no longer available.')
      }
    }
    timer = window.setInterval(() => void check(), 15_000)
    document.addEventListener('visibilitychange', check)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', check)
    }
  }, [invite, publicId])

  const unlock = async () => {
    setBusy(true)
    setMessage('')
    try {
      await unlockClassroomInvite(publicId, accessCode, displayName)
      await load()
    } catch (caught) {
      setMessage(caught instanceof ApiError && caught.status === 429
        ? 'Too many attempts. Wait a few minutes and try again.'
        : 'The invitation or access code is unavailable.')
    } finally { setBusy(false) }
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
      {slide ? <OpenSeadragonViewer tileSource={classroomSlideSource(slide.tileSource, invite.sessionId)} onReady={() => undefined} /> : null}
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
