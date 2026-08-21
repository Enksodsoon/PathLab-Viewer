import { ArrowLeft, DownloadSimple, Play, Plus, Stop, Trash } from '@phosphor-icons/react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '../api'
import { Brand } from '../components/Brand'
import { Loader } from '../components/Loader'
import {
  createStudyCourse,
  downloadStudyInvitations,
  downloadStudyProgress,
  listStudyCourses,
  listStudyPacks,
  transitionStudyCourse,
} from '../study/api'
import type { StudyCourseSummary, StudyPackSummary } from '../study/types'
import { ThemeControl } from '../theme/ThemeControl'
import './StudyAdminPage.css'
import './StudyAdminPilot.css'

export function StudyAdminPage() {
  const [packs, setPacks] = useState<StudyPackSummary[]>([])
  const [courses, setCourses] = useState<StudyCourseSummary[]>([])
  const [packId, setPackId] = useState('')
  const [title, setTitle] = useState('')
  const [retention, setRetention] = useState(30)
  const [learnerLimit, setLearnerLimit] = useState(500)
  const [aiMode, setAiMode] = useState<'deterministic' | 'closed_pilot_trace_sim'>('deterministic')
  const [pilotAcknowledged, setPilotAcknowledged] = useState(false)
  const [inviteCount, setInviteCount] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [nextPacks, nextCourses] = await Promise.all([listStudyPacks(), listStudyCourses()])
      setPacks(nextPacks); setCourses(nextCourses)
      setPackId((current) => current || nextPacks[0]?.id || '')
    } catch (caught) {
      setError(caught instanceof ApiError && caught.status === 401
        ? 'Sign in to Viewer Admin before opening Study Coach.'
        : caught instanceof Error ? caught.message : 'Study Coach is unavailable.')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const create = async () => {
    if (!packId || !title.trim()) return
    setBusy('create'); setError('')
    try {
      await createStudyCourse({ packId, title: title.trim(), retentionDays: retention, learnerLimit, aiMode, pilotAcknowledged })
      setTitle(''); await refresh()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Course creation failed.') }
    finally { setBusy('') }
  }

  const transition = async (course: StudyCourseSummary, action: 'prepare' | 'activate' | 'end' | 'purge') => {
    setBusy(`${course.id}:${action}`); setError('')
    try { await transitionStudyCourse(course.id, action); await refresh() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Course update failed.') }
    finally { setBusy('') }
  }

  const invitations = async (course: StudyCourseSummary) => {
    const count = inviteCount[course.id] ?? Math.min(20, course.learnerLimit - course.invitations)
    setBusy(`${course.id}:invites`); setError('')
    try { await downloadStudyInvitations(course.id, count); await refresh() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Invitation export failed.') }
    finally { setBusy('') }
  }

  return <main className="study-admin">
    <header className="study-admin-topbar"><Brand product="Study" /><nav><Link to="/admin"><ArrowLeft aria-hidden="true" /> Slide library</Link><ThemeControl /></nav></header>
    <section className="study-admin-heading"><div><span>Educational beta</span><h1>Study Coach</h1><p>Viewer now owns Study Pack authoring, faculty preview, courses, and browser-local TRACE-SIM pilots.</p></div><nav className="study-admin-heading-actions"><Link to="/admin/study/packs/new"><Plus /> Author Study Pack</Link><a href="/study" target="_blank" rel="noreferrer">Open learner entry</a></nav></section>
    {error ? <p role="alert" className="study-admin-error">{error}</p> : null}
    {loading ? <Loader label="Loading Study Coach…" /> : <>
      <section className="study-admin-card" aria-labelledby="new-course-heading">
        <h2 id="new-course-heading">New course</h2>
        {packs.length ? <div className="study-admin-form">
          <label>Study Pack<select value={packId} onChange={(event) => setPackId(event.target.value)}>{packs.map((pack) => <option value={pack.id} key={pack.id}>{pack.title} · v{pack.version}</option>)}</select></label>
          <label>Course title<input value={title} maxLength={240} onChange={(event) => setTitle(event.target.value)} /></label>
          <label>Retention days<input type="number" min="0" max="90" value={retention} onChange={(event) => setRetention(Number(event.target.value))} /></label>
          <label>Learner limit<input type="number" min="1" max="500" value={learnerLimit} onChange={(event) => setLearnerLimit(Number(event.target.value))} /></label>
          <label>Guidance mode<select value={aiMode} onChange={(event) => { setAiMode(event.target.value as typeof aiMode); setPilotAcknowledged(false) }}><option value="deterministic">Deterministic faculty guidance</option><option value="closed_pilot_trace_sim">Closed TRACE-SIM pilot</option></select></label>
          {aiMode === 'closed_pilot_trace_sim' ? <label className="study-pilot-ack"><input type="checkbox" checked={pilotAcknowledged} onChange={(event) => setPilotAcknowledged(event.target.checked)} /> I acknowledge this private pilot uses an unapproved experimental model trained only on simulated learners.</label> : null}
          <button type="button" disabled={busy === 'create' || !title.trim() || (aiMode === 'closed_pilot_trace_sim' && !pilotAcknowledged)} onClick={() => void create()}><Plus aria-hidden="true" /> Create draft</button>
        </div> : <p>No Study Packs are available. <Link to="/admin/study/packs/new">Author and faculty-preview one directly in Viewer.</Link></p>}
      </section>
      <section className="study-admin-courses" aria-labelledby="courses-heading"><h2 id="courses-heading">Courses</h2>{courses.length ? courses.map((course) => <article key={course.id}>
        <div><span className={`study-course-state ${course.status}`}>{course.status}</span><h3>{course.title}</h3><p>{course.redeemed} redeemed · {course.invitations} invitations · {course.retentionDays}-day retention</p><p>{course.aiMode === 'closed_pilot_trace_sim' ? 'Closed pilot — unapproved model trained on simulated learners' : 'Deterministic faculty guidance'}</p><p>Device checks: {course.readiness.ready} ready, {course.readiness.fallback} deterministic fallback</p>{course.aiMode === 'closed_pilot_trace_sim' ? <p>Aggregate local-AI actions: {Object.entries(course.aiActions).map(([action, count]) => `${action} ${count}`).join(' · ')}</p> : null}</div>
        <div className="study-course-controls">
          {course.status === 'draft' || course.status === 'preparation' ? <><label>New codes<input type="number" min="1" max={course.learnerLimit - course.invitations} value={inviteCount[course.id] ?? Math.min(20, course.learnerLimit - course.invitations)} onChange={(event) => setInviteCount((current) => ({ ...current, [course.id]: Number(event.target.value) }))} /></label><button type="button" disabled={busy !== '' || course.invitations >= course.learnerLimit} onClick={() => void invitations(course)}><DownloadSimple aria-hidden="true" /> Export one-time codes</button></> : null}
          {course.status === 'draft' ? <button type="button" disabled={busy !== ''} onClick={() => void transition(course, 'prepare')}><Play aria-hidden="true" /> Start preparation</button> : null}
          {course.status === 'preparation' ? <button type="button" disabled={busy !== '' || course.invitations < 1} onClick={() => void transition(course, 'activate')}><Play aria-hidden="true" /> Activate {course.aiMode === 'closed_pilot_trace_sim' ? 'closed pilot' : 'deterministic course'}</button> : null}
          {course.status === 'preparation' || course.status === 'active' ? <button type="button" disabled={busy !== ''} onClick={() => void transition(course, 'end')}><Stop aria-hidden="true" /> End course</button> : null}
          {course.status === 'ended' ? <button type="button" disabled={busy !== ''} onClick={() => void transition(course, 'purge')}><Trash aria-hidden="true" /> Purge now</button> : null}
          {course.redeemed > 0 ? <button type="button" onClick={() => downloadStudyProgress(course.id)}><DownloadSimple aria-hidden="true" /> Export pseudonymous progress</button> : null}
        </div>
      </article>) : <p>No courses yet.</p>}</section>
    </>}
  </main>
}
