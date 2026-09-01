import OpenSeadragon from 'openseadragon'
import { Copy, FolderOpen, ShareNetwork } from '@phosphor-icons/react'
import { QRCodeSVG } from 'qrcode.react'
import {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { ApiError, listSlides } from '../api'
import { classFolderOptions, loadAllLibraryFolders } from '../assessment/classFolders'
import {
  answerQuestion,
  clearTeacherPointer,
  clearTeachingAnnotations,
  classroomReadiness,
  createClassroom,
  endActiveClassroom,
  endClassroom,
  finishLiveClassroom,
  grantControl,
  listClassrooms,
  openQuestion,
  publishTeacherPointer,
  publishTeacherViewport,
  publishTeachingAnnotation,
  removeTeachingAnnotation,
  revokeControl,
  startLiveClassroom,
  teacherParticipants,
  teacherState,
  type ClassroomParticipant,
  type ClassroomReadiness,
  type CreatedClassroom,
  type TeacherParticipantsPage,
  type TeacherState,
  type TeachingAnnotation,
} from '../classroom/api'
import { ClassroomPinOverlays, type ClassroomVisiblePin } from '../classroom/ClassroomPinOverlays'
import { ClassroomSlideNavigator } from '../classroom/ClassroomSlideNavigator'
import { ClassroomTeachingOverlays, type ClassroomTeachingOverlayHandle } from '../classroom/ClassroomTeachingOverlays'
import { createLatestSender } from '../classroom/latestSender'
import { applyPresenterViewport, readPresenterViewport } from '../classroom/presenterViewport'
import { createRosterReconciler } from '../classroom/roster'
import {
  createClassroomSnapshotReconciler,
  type ClassroomSnapshotReconciler,
} from '../classroom/snapshotReconciler'
import { classroomSlideSource } from '../classroom/slideSource'
import {
  applyClassroomStreamEvent,
  createClassroomStreamCursor,
  noteClassroomSnapshot,
} from '../classroom/streamSync'
import {
  StudentDrawingOverlay,
  type DrawingStroke,
} from '../classroom/StudentDrawingOverlay'
import { Brand } from '../components/Brand'
import {
  OpenSeadragonViewer,
  type ViewerAttachmentCallback,
} from '../components/OpenSeadragonViewer'
import { ThemeControl } from '../theme/ThemeControl'
import type { AdminSlide, LibraryFolder } from '../types'
import { CLASSROOM_VIEWER_NETWORK_PROFILE } from '../viewerNetwork'
import '../classroom/classroom.css'

const ACTIVE_CLASSROOM_KEY = 'pathlab-active-classroom:v1'

function defaultReviewExpiry(): string {
  const value = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset())
  return value.toISOString().slice(0, 16)
}

function InviteDialog({ classroom, onClose }: { classroom: CreatedClassroom; onClose: () => void }) {
  const inviteUrl = `${window.location.origin}/classroom/invite/${classroom.publicId}`
  const invitation = `PathLab Classroom\n${inviteUrl}\nAccess code: ${classroom.joinCode}`
  const [message, setMessage] = useState('')
  const copy = async (text: string, success: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setMessage(success)
    } catch { setMessage('Copy failed. Select the visible link and code.') }
  }
  return <div className="classroom-code-display" role="dialog" aria-modal="true" aria-labelledby="classroom-code-title">
    <div className="classroom-invite-card">
      <p>PathLab classroom</p>
      <h2 id="classroom-code-title">Review slides and join class</h2>
      <QRCodeSVG value={inviteUrl} size={232} level="M" aria-label="Classroom invite QR code" />
      <a className="classroom-invite-link" href={inviteUrl}>{inviteUrl}</a>
      <span>Access code</span><strong>{classroom.joinCode}</strong>
      <div className="classroom-invite-actions">
        <button type="button" onClick={() => void copy(inviteUrl, 'Link copied.')}><Copy />Copy link</button>
        <button type="button" onClick={() => void copy(invitation, 'Invitation copied.')}><Copy />Copy invitation</button>
        {'share' in navigator ? <button type="button" onClick={() => void navigator.share({ title: 'PathLab Classroom', text: invitation })}><ShareNetwork />Share</button> : null}
      </div>
      {message ? <span role="status">{message}</span> : null}
      <button type="button" autoFocus onClick={onClose}>Close</button>
    </div>
  </div>
}

function TeachingToolIcon({ name }: { name: 'guide' | 'navigate' | 'draw' | 'arrow' }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {name === 'guide' ? <><circle cx="12" cy="12" r="2" fill="currentColor" /><path d="M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.5 5.5a9.2 9.2 0 0 0 0 13M18.5 5.5a9.2 9.2 0 0 1 0 13" /></> : null}
    {name === 'navigate' ? <path d="m5 3 13.5 9-6.1 1.2L9.5 19 5 3Z" fill="currentColor" /> : null}
    {name === 'draw' ? <><path d="m4 20 4.2-1 10.4-10.4-3.2-3.2L5 15.8 4 20Z" /><path d="m13.8 7 3.2 3.2" /></> : null}
    {name === 'arrow' ? <><path d="M5 19 19 5" strokeWidth="2.8" /><path d="M10 5h9v9" strokeWidth="2.8" /></> : null}
  </svg>
}

function ClassroomPanelIcon({ name }: { name: 'students' | 'questions' | 'marks' | 'locate' | 'check' | 'remove' | 'clear' | 'control' }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {name === 'students' ? <><circle cx="9" cy="8" r="3" /><path d="M3.5 19v-1.5A4.5 4.5 0 0 1 8 13h2a4.5 4.5 0 0 1 4.5 4.5V19M16 5.5a3 3 0 0 1 0 5.8M17 14a4 4 0 0 1 3.5 4" /></> : null}
    {name === 'questions' ? <><path d="M5 5.5h14v10H9l-4 3v-13Z" /><path d="M10 9a2 2 0 1 1 3.5 1.3c-.9.7-1.5 1.1-1.5 2M12 14h.01" /></> : null}
    {name === 'marks' ? <><path d="m4 20 4-1 11-11-3-3L5 16l-1 4Z" /><path d="m14 7 3 3" /></> : null}
    {name === 'locate' ? <><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></> : null}
    {name === 'check' ? <path d="m5 12 4 4L19 6" /> : null}
    {name === 'remove' ? <><path d="M6 7h12M9 7V4h6v3M8 7l1 13h6l1-13M11 11v5M13 11v5" /></> : null}
    {name === 'clear' ? <><path d="M4 7h16M8 7V4h8v3M7 7l1 13h8l1-13" /><path d="M10 11v5M14 11v5" /></> : null}
    {name === 'control' ? <path d="m5 3 13.5 9-6.1 1.2L9.5 19 5 3Z" fill="currentColor" /> : null}
  </svg>
}

function savedClassroom(): CreatedClassroom | null {
  try {
    const value = sessionStorage.getItem(ACTIVE_CLASSROOM_KEY)
    if (!value) return null
    const parsed = JSON.parse(value) as CreatedClassroom
    return { ...parsed, publicId: parsed.publicId ?? null, phase: parsed.phase ?? 'live', reviewExpiresAt: parsed.reviewExpiresAt ?? null }
  } catch {
    return null
  }
}

export function ClassroomTeacherPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const lockedFolderId = searchParams.get('folderId') ?? ''
  const classId = searchParams.get('classId') ?? ''
  const courseId = searchParams.get('courseId') ?? ''
  const classReturnPath = classId && courseId
    ? `/admin/assessments/courses/${courseId}/classes/${classId}`
    : '/admin'
  const [slides, setSlides] = useState<AdminSlide[]>([])
  const [folders, setFolders] = useState<LibraryFolder[]>([])
  const [selectedFolderId, setSelectedFolderId] = useState(lockedFolderId)
  const [reviewExpiry, setReviewExpiry] = useState(defaultReviewExpiry)
  const [readiness, setReadiness] = useState<ClassroomReadiness | null>(null)
  const [recentClassrooms, setRecentClassrooms] = useState<Array<{
    id: string; publicId: string; phase: 'preview' | 'live' | 'review' | 'revoked'; joinCode: string; reviewExpiresAt: string
  }>>([])
  const [setupLoading, setSetupLoading] = useState(true)
  const [classroom, setClassroom] = useState<CreatedClassroom | null>(savedClassroom)
  const [state, setState] = useState<TeacherState | null>(null)
  const [roster, setRoster] = useState<TeacherParticipantsPage>({
    items: [], total: 0, nextCursor: null, rosterVersion: 0,
  })
  const [rosterQuery, setRosterQuery] = useState('')
  const deferredRosterQuery = useDeferredValue(rosterQuery.trim())
  const [rosterLoading, setRosterLoading] = useState(false)
  const [pinnedControlRequests, setPinnedControlRequests] = useState<ClassroomParticipant[]>([])
  const [pendingControlPage, setPendingControlPage] = useState<{
    total: number
    nextCursor: string | null
  }>({ total: 0, nextCursor: null })
  const [pendingControlLoading, setPendingControlLoading] = useState(false)
  const [slideId, setSlideId] = useState('')
  const [error, setError] = useState('')
  const [activeConflict, setActiveConflict] = useState(false)
  const [showCode, setShowCode] = useState(false)
  const [focusedQuestion, setFocusedQuestion] = useState<TeacherState['pendingQuestions'][number] | null>(null)
  const [viewer, setViewer] = useState<OpenSeadragon.Viewer | null>(null)
  const [teachingTool, setTeachingTool] = useState<'navigate' | 'draw' | 'pointer'>('navigate')
  const [pointerColor, setPointerColor] = useState<'green' | 'red'>('green')
  const [guideMode, setGuideMode] = useState(false)
  const suppressPublish = useRef(false)
  const stateRef = useRef<TeacherState | null>(null)
  const presenterRef = useRef<TeacherState['presenter'] | null>(null)
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)
  const slideIdRef = useRef(slideId)
  const streamCursor = useRef(createClassroomStreamCursor(0))
  const snapshotReconciler = useRef<ClassroomSnapshotReconciler | null>(null)
  const snapshotSession = useRef('')
  const rosterRef = useRef(roster)
  const rosterQueryRef = useRef('')
  const rosterLoadedQueryRef = useRef('')
  const rosterRequest = useRef(0)
  const pendingControlRequest = useRef(0)
  const teachingToolRef = useRef(teachingTool)
  const guideModeRef = useRef(guideMode)
  const pointerColorRef = useRef(pointerColor)
  const teachingOverlayRef = useRef<ClassroomTeachingOverlayHandle | null>(null)
  const adminAuthFailed = useRef(false)
  const localPointerElementRef = useRef<HTMLElement | null>(null)

  useEffect(() => { stateRef.current = state }, [state])
  useEffect(() => { rosterRef.current = roster }, [roster])
  useEffect(() => { slideIdRef.current = slideId }, [slideId])
  useEffect(() => { teachingToolRef.current = teachingTool }, [teachingTool])
  useEffect(() => { guideModeRef.current = guideMode }, [guideMode])
  useEffect(() => { pointerColorRef.current = pointerColor }, [pointerColor])

  const handleAdminFailure = useCallback((caught: unknown, message: string) => {
    if (caught instanceof ApiError && caught.status === 401) {
      adminAuthFailed.current = true
      guideModeRef.current = false
      setGuideMode(false)
      sessionStorage.removeItem('pathlab-csrf')
      navigate('/admin', { replace: true })
      return true
    }
    setError(message)
    return false
  }, [navigate])
  useEffect(() => {
    if (!showCode) return
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setShowCode(false)
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [showCode])

  useEffect(() => {
    let cancelled = false
    void Promise.all([listSlides(), loadAllLibraryFolders()])
      .then(([items, library]) => {
        if (cancelled) return
        setSlides(items)
        setFolders(library.folders)
      })
      .catch((loadError: unknown) => {
        if (cancelled) return
        if (loadError instanceof ApiError && loadError.status === 401) {
          navigate('/admin', { replace: true })
          return
        }
        setError('Class folders could not be loaded.')
      })
      .finally(() => {
        if (!cancelled) setSetupLoading(false)
      })
    return () => { cancelled = true }
  }, [navigate])

  useEffect(() => {
    if (classroom) return
    void listClassrooms().then((result) => setRecentClassrooms(result.sessions)).catch(() => undefined)
  }, [classroom])

  const folderOptions = useMemo(
    () => classFolderOptions(folders, slides),
    [folders, slides],
  )
  const selected = useMemo(
    () => folderOptions.find((option) => option.folder.id === selectedFolderId)?.slides.map((slide) => slide.id) ?? [],
    [folderOptions, selectedFolderId],
  )

  useEffect(() => {
    if (!selectedFolderId || classroom) {
      setReadiness(null)
      return
    }
    let active = true
    void classroomReadiness(selectedFolderId).then((next) => {
      if (active) setReadiness(next)
    }).catch(() => {
      if (active) setError('This folder could not be checked for classroom readiness.')
    })
    return () => { active = false }
  }, [classroom, selectedFolderId])

  const refresh = useCallback((sessionId: string, minimumVersion = 0): Promise<void> => {
    if (!snapshotReconciler.current || snapshotSession.current !== sessionId) {
      snapshotReconciler.current?.dispose()
      snapshotSession.current = sessionId
      snapshotReconciler.current = createClassroomSnapshotReconciler(
        () => teacherState(sessionId),
        (next) => {
          noteClassroomSnapshot(streamCursor.current, next.stateVersion)
          presenterRef.current = next.presenter
          stateRef.current = next
          setState(next)
          teachingOverlayRef.current?.setPointer(
            teachingToolRef.current === 'pointer' ? null : next.teacherPointer,
          )
          if (next.presenter.slideId) setSlideId(next.presenter.slideId)
        },
      )
    }
    return snapshotReconciler.current.request(minimumVersion)
  }, [])

  useEffect(() => () => snapshotReconciler.current?.dispose(), [])

  const refreshRoster = useCallback(async (
    sessionId: string,
    minimumVersion?: number,
  ) => {
    const query = rosterQueryRef.current
    if (minimumVersion !== undefined
      && rosterLoadedQueryRef.current === query
      && minimumVersion <= rosterRef.current.rosterVersion) return
    const request = ++rosterRequest.current
    setRosterLoading(true)
    try {
      const next = await teacherParticipants(sessionId, { limit: 100, q: query })
      if (request !== rosterRequest.current || query !== rosterQueryRef.current) return
      rosterLoadedQueryRef.current = query
      rosterRef.current = next
      setRoster(next)
      setPinnedControlRequests((current) => current.flatMap((participant) => {
        const fresh = next.items.find((item) => item.id === participant.id)
        if (!fresh) return [participant]
        return fresh.controlRequested ? [fresh] : []
      }))
    } finally {
      if (request === rosterRequest.current) setRosterLoading(false)
    }
  }, [])

  const refreshPendingControlRequests = useCallback(async (sessionId: string) => {
    const request = ++pendingControlRequest.current
    setPendingControlLoading(true)
    try {
      const next = await teacherParticipants(sessionId, { limit: 100, requested: true })
      if (request !== pendingControlRequest.current) return
      setPinnedControlRequests(next.items.filter((participant) => participant.controlRequested))
      setPendingControlPage({ total: next.total, nextCursor: next.nextCursor })
    } finally {
      if (request === pendingControlRequest.current) setPendingControlLoading(false)
    }
  }, [])

  const loadMorePendingControlRequests = useCallback(async (sessionId: string) => {
    const { nextCursor } = pendingControlPage
    if (!nextCursor || pendingControlLoading) return
    const request = ++pendingControlRequest.current
    setPendingControlLoading(true)
    try {
      const next = await teacherParticipants(sessionId, {
        after: nextCursor,
        limit: 100,
        requested: true,
      })
      if (request !== pendingControlRequest.current) return
      setPinnedControlRequests((current) => {
        const byId = new Map(current.map((participant) => [participant.id, participant]))
        for (const participant of next.items) {
          if (participant.controlRequested) byId.set(participant.id, participant)
        }
        return [...byId.values()]
      })
      setPendingControlPage({ total: next.total, nextCursor: next.nextCursor })
    } finally {
      if (request === pendingControlRequest.current) setPendingControlLoading(false)
    }
  }, [pendingControlLoading, pendingControlPage])

  const loadMoreRoster = useCallback(async (sessionId: string) => {
    const { nextCursor } = rosterRef.current
    if (!nextCursor || rosterLoading) return
    const query = rosterQueryRef.current
    const request = ++rosterRequest.current
    setRosterLoading(true)
    try {
      const next = await teacherParticipants(sessionId, {
        after: nextCursor,
        limit: 100,
        q: query,
      })
      if (request !== rosterRequest.current || query !== rosterQueryRef.current) return
      setRoster((current) => {
        const byId = new Map(current.items.map((participant) => [participant.id, participant]))
        for (const participant of next.items) byId.set(participant.id, participant)
        const merged = {
          ...next,
          items: [...byId.values()],
        }
        rosterRef.current = merged
        return merged
      })
      setPinnedControlRequests((current) => current.flatMap((participant) => {
        const fresh = next.items.find((item) => item.id === participant.id)
        if (!fresh) return [participant]
        return fresh.controlRequested ? [fresh] : []
      }))
    } finally {
      if (request === rosterRequest.current) setRosterLoading(false)
    }
  }, [rosterLoading])

  useEffect(() => {
    rosterQueryRef.current = deferredRosterQuery
    if (!classroom || classroom.phase !== 'live') return
    void refreshRoster(classroom.id).catch((caught: unknown) => {
      handleAdminFailure(caught, 'The student roster could not be loaded.')
    })
  }, [classroom, deferredRosterQuery, handleAdminFailure, refreshRoster])

  useEffect(() => {
    if (!classroom || classroom.phase !== 'live') return
    void refreshPendingControlRequests(classroom.id).catch((caught: unknown) => {
      handleAdminFailure(caught, 'Pending control requests could not be loaded.')
    })
  }, [classroom, handleAdminFailure, refreshPendingControlRequests])

  useEffect(() => {
    if (!classroom) return
    if (state?.session.id !== classroom.id) {
      void refresh(classroom.id).catch((loadError: unknown) => {
        if (loadError instanceof ApiError && loadError.status === 404) {
          sessionStorage.removeItem(ACTIVE_CLASSROOM_KEY)
          setClassroom(null)
          setError('The previous classroom is no longer active.')
          return
        }
        setError('The classroom connection was interrupted. Reconnecting…')
      })
      return
    }
    if (classroom.phase !== 'live') return
    const events = new EventSource(`/api/v1/admin/classroom/sessions/${classroom.id}/events`)
    const rosterReconciler = createRosterReconciler(async (version) => {
      try {
        await Promise.all([
          refreshRoster(classroom.id, version),
          refreshPendingControlRequests(classroom.id),
        ])
      } catch (caught) {
        handleAdminFailure(caught, 'The student roster could not be refreshed.')
      }
    })
    let streamReadySeen = false
    const sequence = (event: Event, coalescible = false): Record<string, unknown> | null => {
      try {
        const payload = JSON.parse((event as MessageEvent<string>).data) as Record<string, unknown>
        const decision = applyClassroomStreamEvent(
          streamCursor.current,
          event.type,
          payload,
          { coalescible },
        )
        if (decision === 'resync') {
          void refresh(
            classroom.id,
            typeof payload.stateVersion === 'number' ? payload.stateVersion : 0,
          ).catch(() => undefined)
          return null
        }
        return decision === 'apply' ? payload : null
      } catch {
        void refresh(classroom.id).catch(() => undefined)
        return null
      }
    }
    const update = (event: Event) => {
      if (sequence(event)) void refresh(classroom.id).catch(() => undefined)
    }
    events.addEventListener('stream-ready', (event) => {
      sequence(event)
      if (streamReadySeen) {
        rosterReconciler.notify(rosterRef.current.rosterVersion + 1)
      }
      streamReadySeen = true
    })
    for (const name of ['question-added', 'question-removed', 'control']) {
      events.addEventListener(name, update)
    }
    events.addEventListener('roster-changed', (event) => {
      const payload = sequence(event)
      let rosterVersion = payload?.rosterVersion
      if (typeof rosterVersion !== 'number') {
        try {
          const raw = JSON.parse((event as MessageEvent<string>).data) as Record<string, unknown>
          rosterVersion = raw.rosterVersion
        } catch {
          rosterVersion = undefined
        }
      }
      if (typeof rosterVersion === 'number') {
        rosterReconciler.notify(rosterVersion)
      }
    })
    events.addEventListener('presenter', (event) => {
      const payload = sequence(event, true)
      if (!payload || typeof payload.presenterSequence !== 'number'
        || typeof payload.slideId !== 'string' || !payload.viewport) return
      if (!stateRef.current?.controller.participantId) return
      const nextPresenter: TeacherState['presenter'] = {
        sequence: payload.presenterSequence as number,
        slideId: payload.slideId as string,
        viewport: payload.viewport as TeacherState['presenter']['viewport'],
      }
      presenterRef.current = nextPresenter
      if (slideIdRef.current !== nextPresenter.slideId) {
        slideIdRef.current = nextPresenter.slideId ?? ''
        setSlideId(nextPresenter.slideId ?? '')
        return
      }
      const target = viewerRef.current
      const slide = classroom.slides.find((item) => item.id === nextPresenter.slideId)
      if (!target || !slide || !nextPresenter.viewport) return
      suppressPublish.current = true
      applyPresenterViewport(target, slide, nextPresenter.viewport)
      window.setTimeout(() => { suppressPublish.current = false }, 0)
    })
    events.addEventListener('pointer', (event) => {
      const payload = sequence(event, true)
      if (!payload || typeof payload.slideId !== 'string'
        || typeof payload.style !== 'string' || typeof payload.x !== 'number'
        || typeof payload.y !== 'number') return
      const nextPointer = payload as unknown as TeacherState['teacherPointer']
      // The teacher already has a zero-latency screen-space pointer. Ignore the
      // server echo locally while pointer mode is active so it cannot render a
      // delayed second arrow; students still receive and project this event.
      if (teachingToolRef.current !== 'pointer') {
        teachingOverlayRef.current?.setPointer(nextPointer)
      }
      if (stateRef.current) stateRef.current.teacherPointer = nextPointer
    })
    events.addEventListener('pointer-removed', (event) => {
      if (!sequence(event)) return
      teachingOverlayRef.current?.setPointer(null)
      if (stateRef.current) stateRef.current.teacherPointer = null
    })
    events.addEventListener('teaching-annotation-added', (event) => {
      const payload = sequence(event)
      const annotation = payload?.annotation as TeachingAnnotation | undefined
      if (!annotation?.id) return
      setState((current) => current ? {
        ...current,
        teachingAnnotations: [
          ...(current.teachingAnnotations ?? []).filter((item) => item.id !== annotation.id),
          annotation,
        ].slice(-40),
      } : current)
    })
    events.addEventListener('teaching-annotation-removed', (event) => {
      const payload = sequence(event)
      if (!payload || typeof payload.annotationId !== 'string') return
      setState((current) => current ? {
        ...current,
        teachingAnnotations: (current.teachingAnnotations ?? []).filter(
          (item) => item.id !== payload.annotationId,
        ),
      } : current)
    })
    events.addEventListener('teaching-annotations-cleared', (event) => {
      if (!sequence(event)) return
      setState((current) => current ? { ...current, teachingAnnotations: [] } : current)
    })
    events.addEventListener('pin-updated', (event) => {
      const payload = sequence(event)
      if (!payload || typeof payload.participantId !== 'string'
        || typeof payload.alias !== 'string' || typeof payload.slideId !== 'string'
        || typeof payload.x !== 'number' || typeof payload.y !== 'number'
        || typeof payload.zoom !== 'number') return
      const pin = payload as unknown as TeacherState['activePins'][number]
      setState((current) => current ? {
        ...current,
        activePins: [...current.activePins.filter(
          (item) => item.participantId !== pin.participantId,
        ), pin],
      } : current)
    })
    events.addEventListener('pin-removed', (event) => {
      const payload = sequence(event)
      if (!payload || typeof payload.participantId !== 'string') return
      setState((current) => current ? {
        ...current,
        activePins: current.activePins.filter(
          (item) => item.participantId !== payload.participantId,
        ),
      } : current)
    })
    const updateControlRequest = (event: Event, requested: boolean) => {
      const previousEpoch = streamCursor.current.hubEpoch
      const previousSequence = streamCursor.current.eventSequence
      let raw: Record<string, unknown>
      try {
        raw = JSON.parse((event as MessageEvent<string>).data) as Record<string, unknown>
      } catch {
        sequence(event)
        return
      }
      const sequenced = sequence(event)
      const rawEpoch = typeof raw.hubEpoch === 'string' ? raw.hubEpoch : ''
      const rawSequence = typeof raw.eventSequence === 'number' ? raw.eventSequence : -1
      const duplicate = rawEpoch === previousEpoch && rawSequence <= previousSequence
      if (!sequenced && (duplicate || !rawEpoch || !Number.isSafeInteger(rawSequence))) return
      const payload = sequenced ?? raw
      if (typeof payload.participantId !== 'string') return
      pendingControlRequest.current += 1
      setPendingControlLoading(false)
      const participantId = payload.participantId
      const eventParticipant = payload.participant as Partial<ClassroomParticipant> | undefined
      const authoritative = eventParticipant
        && eventParticipant.id === participantId
        && typeof eventParticipant.alias === 'string'
        && (eventParticipant.status === 'connected'
          || eventParticipant.status === 'reconnecting'
          || eventParticipant.status === 'disconnected')
        ? {
            id: participantId,
            alias: eventParticipant.alias,
            displayName: typeof eventParticipant.displayName === 'string'
              ? eventParticipant.displayName
              : null,
            status: eventParticipant.status,
            controlRequested: true,
            controlRequestedAt: typeof eventParticipant.controlRequestedAt === 'number'
              ? eventParticipant.controlRequestedAt
              : Date.now(),
          }
        : null
      const known = rosterRef.current.items.find((participant) => participant.id === participantId)
        ?? stateRef.current?.participants.find((participant) => participant.id === participantId)
      setPinnedControlRequests((current) => {
        if (!requested) return current.filter((participant) => participant.id !== participantId)
        const participant = authoritative ?? known ?? current.find(
          (item) => item.id === participantId,
        )
        if (!participant) return current
        return [{
          ...participant,
          controlRequested: true,
          controlRequestedAt: participant.controlRequestedAt ?? Date.now(),
        }, ...current.filter((item) => item.id !== participantId)]
      })
      setRoster((current) => {
        const next = {
          ...current,
          items: current.items.map((participant) => participant.id === participantId
            ? {
                ...participant,
                controlRequested: requested,
                controlRequestedAt: requested ? Date.now() : null,
              }
            : participant),
        }
        rosterRef.current = next
        return next
      })
    }
    events.addEventListener('control-requested', (event) => updateControlRequest(event, true))
    events.addEventListener('control-request-cancelled', (event) => updateControlRequest(event, false))
    return () => {
      rosterReconciler.dispose()
      events.close()
    }
  }, [
    classroom,
    handleAdminFailure,
    refresh,
    refreshPendingControlRequests,
    refreshRoster,
    state?.session.id,
  ])

  const currentSlide = useMemo(
    () => classroom?.slides.find((slide) => slide.id === slideId) ?? classroom?.slides[0],
    [classroom, slideId],
  )

  const participants = useMemo(() => {
    const pinnedIds = new Set(pinnedControlRequests.map((participant) => participant.id))
    return [...pinnedControlRequests, ...roster.items.filter(
      (participant) => !pinnedIds.has(participant.id),
    )].sort((left, right) => {
    if (left.controlRequested !== right.controlRequested) return left.controlRequested ? -1 : 1
    return (left.controlRequestedAt ?? Number.POSITIVE_INFINITY)
      - (right.controlRequestedAt ?? Number.POSITIVE_INFINITY)
    })
  }, [pinnedControlRequests, roster.items])
  const activeParticipantCount = roster.total || state?.participantCount || participants.length

  const visiblePins = useMemo<ClassroomVisiblePin[]>(() => {
    const pins: ClassroomVisiblePin[] = focusedQuestion ? [{
      participantId: focusedQuestion.participantId,
      alias: state?.participants.find((item) => item.id === focusedQuestion.participantId)?.alias ?? 'Question',
      slideId: focusedQuestion.slideId,
      x: focusedQuestion.x,
      y: focusedQuestion.y,
      focused: true,
    }] : []
    pins.push(...(state?.activePins ?? []))
    return pins
  }, [focusedQuestion, state?.activePins, state?.participants])

  const applyRemote = useCallback((target: OpenSeadragon.Viewer) => {
    const current = stateRef.current
    const presenter = presenterRef.current
    const slide = classroom?.slides.find((item) => item.id === slideIdRef.current)
    if (!presenter?.viewport || presenter.slideId !== slide?.id || !slide) return
    suppressPublish.current = true
    applyPresenterViewport(target, slide, presenter.viewport)
    if (!current?.controller.participantId) {
      window.setTimeout(() => { suppressPublish.current = false }, 250)
    }
  }, [classroom])

  useEffect(() => {
    if (viewer) applyRemote(viewer)
  }, [applyRemote, state?.presenter, viewer])

  useEffect(() => {
    if (!viewer || classroom?.phase !== 'live') return
    // Pointer mode is an additive presentation aid: keep the normal pan, zoom,
    // and touch gestures available while the screen-space arrow follows along.
    try {
      viewer.setMouseNavEnabled(teachingTool !== 'draw')
    } catch {
      // The viewer may already be closing while live teaching transitions to review.
      return
    }
    if (teachingTool === 'pointer') teachingOverlayRef.current?.setPointer(null)
    if (teachingTool !== 'pointer' && localPointerElementRef.current) {
      localPointerElementRef.current.className = 'classroom-local-pointer'
    }
    if (teachingTool === 'pointer') return
    void clearTeacherPointer(classroom.id).catch(() => undefined)
  }, [classroom, teachingTool, viewer])

  const teachingAnnotation = useCallback((stroke: DrawingStroke) => {
    if (!viewer || !currentSlide || !classroom) return false
    const item = viewer.world.getItemAt(0)
    if (!item) return false
    const bounds = viewer.container.getBoundingClientRect()
    const dimensions = item.source.dimensions
    if (stroke.tool === 'eraser') {
      const distanceToSegment = (point: DrawingStroke['points'][number], start: DrawingStroke['points'][number], end: DrawingStroke['points'][number]) => {
        const dx = end.x - start.x
        const dy = end.y - start.y
        const lengthSquared = dx * dx + dy * dy
        const amount = lengthSquared ? Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSquared)) : 0
        return Math.hypot(point.x - (start.x + amount * dx), point.y - (start.y + amount * dy))
      }
      const project = (point: TeachingAnnotation['points'][number]) => {
        const projected = viewer.viewport.viewportToViewerElementCoordinates(
          item.imageToViewportCoordinates(point.x * dimensions.x, point.y * dimensions.y),
        )
        return { x: projected.x / bounds.width, y: projected.y / bounds.height }
      }
      const erased = (stateRef.current?.teachingAnnotations ?? []).filter((annotation) => {
        if (annotation.slideId !== currentSlide.id || !annotation.points.length) return false
        const projected = annotation.points.map(project)
        const first = projected[0]
        const last = projected.at(-1) ?? first
        const outline = annotation.tool === 'rectangle'
          ? [first, { x: last.x, y: first.y }, last, { x: first.x, y: last.y }, first]
          : annotation.tool === 'ellipse'
            ? Array.from({ length: 25 }, (_, index) => {
                const angle = index / 24 * Math.PI * 2
                return {
                  x: (first.x + last.x) / 2 + Math.cos(angle) * Math.abs(last.x - first.x) / 2,
                  y: (first.y + last.y) / 2 + Math.sin(angle) * Math.abs(last.y - first.y) / 2,
                }
              })
            : projected
        const threshold = Math.max(14 / Math.max(1, Math.min(bounds.width, bounds.height)), annotation.width / Math.max(1, bounds.width))
        return stroke.points.some((eraserPoint) => outline.some((point, index) => (
          index === 0
            ? Math.hypot(eraserPoint.x - point.x, eraserPoint.y - point.y) <= threshold
            : distanceToSegment(eraserPoint, outline[index - 1], point) <= threshold
        )))
      })
      if (!erased.length) return true
      return Promise.all(erased.map((annotation) => removeTeachingAnnotation(classroom.id, annotation.id)))
        .then(() => true)
        .catch((caught: unknown) => {
          handleAdminFailure(caught, 'The selected teaching mark could not be erased.')
          return false
        })
    }
    const annotation: TeachingAnnotation = {
      id: stroke.id,
      slideId: currentSlide.id,
      tool: stroke.tool,
      color: stroke.color as TeachingAnnotation['color'],
      width: stroke.width as TeachingAnnotation['width'],
      points: stroke.points.map((point) => {
        const viewportPoint = viewer.viewport.pointFromPixel(new OpenSeadragon.Point(
          point.x * bounds.width,
          point.y * bounds.height,
        ), true)
        const imagePoint = viewer.viewport.viewportToImageCoordinates(viewportPoint)
        return {
          x: Math.round(Math.max(0, Math.min(1, imagePoint.x / dimensions.x)) * 100000) / 100000,
          y: Math.round(Math.max(0, Math.min(1, imagePoint.y / dimensions.y)) * 100000) / 100000,
        }
      }),
    }
    return publishTeachingAnnotation(classroom.id, annotation)
      .then(() => true)
      .catch((caught: unknown) => {
        handleAdminFailure(caught, 'The teaching mark could not be shared. The mark remains visible locally.')
        return false
      })
  }, [classroom, currentSlide, handleAdminFailure, viewer])

  const attachViewer = useCallback<ViewerAttachmentCallback>((viewer) => {
    viewerRef.current = viewer
    setViewer(viewer)
    const localPointer = document.createElement('span')
    localPointer.className = 'classroom-local-pointer'
    localPointerElementRef.current = localPointer
    viewer.container.append(localPointer)
    const sender = createLatestSender(() => (
      publishTeacherViewport(classroom!.id, readPresenterViewport(viewer, currentSlide!.id))
        .then(() => setError((current) => current === 'The live field could not be shared.' ? '' : current))
        .catch((caught: unknown) => {
          handleAdminFailure(caught, 'The live field could not be shared.')
        })
    ))
    const publish = () => {
      if (suppressPublish.current) {
        suppressPublish.current = false
        return
      }
      if (adminAuthFailed.current || !guideModeRef.current || stateRef.current?.controller.participantId
        || !classroom || !currentSlide) return
      sender.push(0)
    }
    const opened = () => applyRemote(viewer)
    let pointerVisible = false
    let localPointerColor: 'green' | 'red' | null = null
    let pointerFrame: number | null = null
    let pendingPointer: { clientX: number; clientY: number; color: 'green' | 'red' } | null = null
    let pointerBounds = viewer.canvas.getBoundingClientRect()
    const updatePointerBounds = () => { pointerBounds = viewer.canvas.getBoundingClientRect() }
    const pointerBoundsObserver = new ResizeObserver(updatePointerBounds)
    pointerBoundsObserver.observe(viewer.canvas)
    const pointerSender = createLatestSender((sample: NonNullable<typeof pendingPointer>) => {
      const item = viewer.world.getItemAt(0)
      if (!item || !classroom || !currentSlide) return Promise.resolve()
      const viewportPoint = viewer.viewport.pointFromPixel(new OpenSeadragon.Point(
        sample.clientX - pointerBounds.left,
        sample.clientY - pointerBounds.top,
      ), true)
      const imagePoint = viewer.viewport.viewportToImageCoordinates(viewportPoint)
      const dimensions = item.source.dimensions
      return publishTeacherPointer(classroom.id, {
        slideId: currentSlide.id,
        style: `${sample.color}-arrow`,
        x: Math.max(0, Math.min(1, imagePoint.x / dimensions.x)),
        y: Math.max(0, Math.min(1, imagePoint.y / dimensions.y)),
      }).catch((caught: unknown) => {
        handleAdminFailure(caught, 'The live pointer could not be shared.')
      })
    }, 100)
    const point = (event: globalThis.PointerEvent) => {
      if (adminAuthFailed.current || !classroom || !currentSlide || teachingToolRef.current !== 'pointer') return
      if (event.buttons !== 0) {
        clearPointer()
        return
      }
      pendingPointer = { clientX: event.clientX, clientY: event.clientY, color: pointerColorRef.current }
      if (pointerFrame !== null) return
      pointerFrame = window.requestAnimationFrame(() => {
        pointerFrame = null
        const sample = pendingPointer
        if (!sample) return
        pendingPointer = null
        if (!pointerVisible || localPointerColor !== sample.color) {
          pointerVisible = true
          localPointerColor = sample.color
          localPointer.className = `classroom-local-pointer is-visible${sample.color === 'red' ? ' is-red' : ''}`
        }
        localPointer.style.transform = `translate3d(${sample.clientX - pointerBounds.left}px, ${sample.clientY - pointerBounds.top}px, 0)`
        pointerSender.push(sample)
      })
    }
    const clearPointer = () => {
      if (!classroom || !pointerVisible) return
      pendingPointer = null
      if (pointerFrame !== null) window.cancelAnimationFrame(pointerFrame)
      pointerFrame = null
      pointerVisible = false
      localPointerColor = null
      localPointer.className = 'classroom-local-pointer'
      if (!adminAuthFailed.current) void clearTeacherPointer(classroom.id).catch(() => undefined)
    }
    viewer.canvas.addEventListener('pointermove', point)
    viewer.canvas.addEventListener('pointerleave', clearPointer)
    viewer.addHandler('open', opened)
    viewer.addHandler('animation', publish)
    viewer.addHandler('animation-finish', publish)
    return () => {
      viewer.removeHandler('open', opened)
      viewer.removeHandler('animation', publish)
      viewer.removeHandler('animation-finish', publish)
      viewer.canvas.removeEventListener('pointermove', point)
      viewer.canvas.removeEventListener('pointerleave', clearPointer)
      pointerBoundsObserver.disconnect()
      if (pointerFrame !== null) window.cancelAnimationFrame(pointerFrame)
      sender.dispose()
      pointerSender.dispose()
      clearPointer()
      localPointer.remove()
      if (localPointerElementRef.current === localPointer) localPointerElementRef.current = null
      if (viewerRef.current === viewer) viewerRef.current = null
      setViewer(null)
    }
  }, [applyRemote, classroom, currentSlide, handleAdminFailure])

  const start = async () => {
    setError('')
    setActiveConflict(false)
    try {
      if (!selectedFolderId) return
      const checked = await classroomReadiness(selectedFolderId)
      setReadiness(checked)
      if (checked.blocked.length) {
        setError(`This folder is blocked: ${checked.blocked.map((item) => item.displayName).join(', ')} must be republished.`)
        return
      }
      const created = await createClassroom(selectedFolderId, new Date(reviewExpiry).toISOString())
      setClassroom(created)
      sessionStorage.setItem(ACTIVE_CLASSROOM_KEY, JSON.stringify(created))
      setSlideId(created.slides[0].id)
      setShowCode(true)
    } catch (startError) {
      if (startError instanceof ApiError && startError.code === 'CLASSROOM_ALREADY_ACTIVE') {
        setError('A classroom is already active. End it before starting another.')
        setActiveConflict(true)
      } else if (startError instanceof ApiError && (startError.code === 'CLASSROOM_SLIDE_NOT_READY' || startError.code === 'CLASSROOM_SLIDES_BLOCKED')) {
        setError('The classroom could not be prepared. One or more slides must be republished.')
      } else {
        setError('The classroom could not start. Try again.')
      }
    }
  }

  if (!classroom) return <main className="classroom-entry classroom-setup">
    <header className="classroom-entry__header">
      <Brand variant="library" />
      <div className="classroom-entry__actions">
        <ThemeControl compact />
        <Link className="classroom-back-link" to={classReturnPath}>{classId ? 'Back to class' : 'Back to library'}</Link>
      </div>
    </header>
    <section className="classroom-entry__card">
      <p className="classroom-kicker">Prepare classroom</p>
      <h1>{lockedFolderId ? 'Prepare this classroom' : 'Choose a class folder'}</h1>
      <p className="classroom-entry__intro">Create one protected link for review before, during, and after class.</p>
      {error && <p role="alert" className="classroom-error">{error}</p>}
      {activeConflict && <button className="classroom-entry__recovery" type="button" onClick={() => void endActiveClassroom().then(() => {
        sessionStorage.removeItem(ACTIVE_CLASSROOM_KEY)
        setActiveConflict(false)
        setError('The previous classroom ended. You can start a new one now.')
      }).catch((endError: unknown) => handleAdminFailure(endError, 'The previous classroom could not be ended. Try again.'))}>
        End existing classroom
      </button>}
      {lockedFolderId ? <div className="classroom-locked-folder" aria-label="Saved class slide set">
        <FolderOpen aria-hidden="true" />
        <span><strong>{folderOptions.find((option) => option.folder.id === lockedFolderId)?.folder.name ?? 'Saved class folder'}</strong><small>{selected.length} {selected.length === 1 ? 'slide' : 'slides'} from this class</small></span>
      </div> : <div className="classroom-folder-picker" role="radiogroup" aria-label="Class folder">
        {setupLoading ? <p className="classroom-folder-picker__status" role="status">Loading class folders…</p> : null}
        {!setupLoading && !folderOptions.length ? (
          <p className="classroom-folder-picker__status">Create a library folder before starting a classroom.</p>
        ) : null}
        {folderOptions.map(({ folder, depth, slides: folderSlides }) => {
          const count = folderSlides.length
          const selectedFolder = selectedFolderId === folder.id
          return <label
            key={folder.id}
            className={selectedFolder ? 'selected' : undefined}
            style={{ '--classroom-folder-depth': depth } as CSSProperties}
          >
            <input
              type="radio"
              name="classroom-folder"
              value={folder.id}
              checked={selectedFolder}
              disabled={count === 0}
              onChange={() => setSelectedFolderId(folder.id)}
            />
            <span className="classroom-folder-picker__icon"><FolderOpen aria-hidden="true" /></span>
            <span className="classroom-folder-picker__copy">
              <strong>{folder.name}</strong>
              <small>{count === 0
                ? 'No slides'
                : `${count} ${count === 1 ? 'slide' : 'slides'}${folder.hasChildren ? ' · includes subfolders' : ''}`}</small>
            </span>
          </label>
        })}
      </div>}
      {readiness?.blocked.length ? <div className="classroom-readiness-error" role="alert">
        <strong>{readiness.blocked.length} slide{readiness.blocked.length === 1 ? '' : 's'} need attention</strong>
        {readiness.blocked.map((item) => <span key={item.id}>{item.displayName} · {item.reason.replaceAll('_', ' ')}</span>)}
      </div> : null}
      <label className="classroom-expiry">Review access expires
        <input type="datetime-local" min={new Date(Date.now() + 60 * 60 * 1000).toISOString().slice(0, 16)} max={new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16)} value={reviewExpiry} onChange={(event) => setReviewExpiry(event.target.value)} />
      </label>
      <button className="primary classroom-entry__primary" type="button" disabled={!selected.length || Boolean(readiness?.blocked.length)} onClick={() => void start()}>
        {selected.length
          ? `Prepare classroom with ${readiness?.ready.length ?? selected.length} ${selected.length === 1 ? 'slide' : 'slides'}`
          : lockedFolderId ? 'This class has no slides' : 'Choose a class folder'}
      </button>
      {recentClassrooms.some((item) => item.phase === 'review') ? <section className="classroom-recent-reviews">
        <h2>Recent review links</h2>
        {recentClassrooms.filter((item) => item.phase === 'review').map((item) => <div key={item.id}>
          <span><strong>{item.joinCode}</strong><small>Expires {new Date(item.reviewExpiresAt).toLocaleString()}</small></span>
          <button type="button" onClick={() => void navigator.clipboard.writeText(`${window.location.origin}/classroom/invite/${item.publicId}`)}>Copy link</button>
          <button type="button" className="danger" onClick={() => void endClassroom(item.id).then(() => setRecentClassrooms((current) => current.filter((entry) => entry.id !== item.id)))}>Revoke</button>
        </div>)}
      </section> : null}
    </section>
  </main>

  if (classroom.phase !== 'live') return <main className="classroom-entry classroom-setup">
    <header className="classroom-entry__header">
      <Brand variant="library" />
      <div className="classroom-entry__actions"><ThemeControl compact /><Link className="classroom-back-link" to={classReturnPath}>{classId ? 'Back to class' : 'Back to library'}</Link></div>
    </header>
    <section className="classroom-entry__card classroom-prepared-card">
      <p className="classroom-kicker">{classroom.phase === 'preview' ? 'Classroom prepared' : 'Post-class review'}</p>
      <h1>{classroom.phase === 'preview' ? 'Invite students to review' : 'Review remains open'}</h1>
      <p className="classroom-entry__intro">The protected link opens all {classroom.slides.length} slides. Students enter the separate access code once.</p>
      <button className="classroom-join-code classroom-join-code--large" type="button" onClick={() => setShowCode(true)}>
        <span>Access code</span><strong>{classroom.joinCode}</strong><small>Display QR and link</small>
      </button>
      {classroom.reviewExpiresAt ? <p className="classroom-review-expiry">Review expires {new Date(classroom.reviewExpiresAt).toLocaleString()}</p> : null}
      <div className="classroom-prepared-actions">
        {classroom.phase === 'preview' ? <button className="primary classroom-entry__primary" type="button" onClick={() => void startLiveClassroom(classroom.id).then(() => {
          const next = { ...classroom, phase: 'live' as const }
          setClassroom(next)
          sessionStorage.setItem(ACTIVE_CLASSROOM_KEY, JSON.stringify(next))
          setShowCode(true)
        }).catch((caught: unknown) => {
          if (caught instanceof ApiError && caught.code === 'CLASSROOM_DRAINING') {
            setError('Background preparation is stopping to protect the live class. Wait a moment, then start again.')
            return
          }
          handleAdminFailure(caught, 'The live class could not start.')
        })}>Start live class</button> : null}
        <button className="classroom-danger-action" type="button" onClick={() => void endClassroom(classroom.id).then(() => {
          sessionStorage.removeItem(ACTIVE_CLASSROOM_KEY)
          setClassroom(null)
        }).catch((caught: unknown) => handleAdminFailure(caught, 'Review access could not be revoked.'))}>Revoke review access</button>
      </div>
      {error ? <p role="alert" className="classroom-error">{error}</p> : null}
    </section>
    {showCode && classroom.publicId ? <InviteDialog classroom={classroom} onClose={() => setShowCode(false)} /> : null}
  </main>

  return <div className="classroom-shell classroom-shell--teacher">
    <header className="classroom-topbar">
      <Brand variant="library" />
      <button className="classroom-join-code" type="button" onClick={() => setShowCode(true)}>
        <span>Join code</span><strong>{classroom.joinCode}</strong><small>Display</small>
      </button>
      <div className="classroom-topbar__actions">
        <ThemeControl compact />
        <button className="classroom-danger-action" type="button" onClick={() => void finishLiveClassroom(classroom.id).then(() => {
          const next = { ...classroom, phase: 'review' as const }
          sessionStorage.setItem(ACTIVE_CLASSROOM_KEY, JSON.stringify(next))
          setClassroom(next)
        })}>
          End class
        </button>
      </div>
    </header>
    <main className="classroom-viewer">
      {currentSlide && <OpenSeadragonViewer
        tileSource={classroomSlideSource(currentSlide.tileSource, classroom.id)}
        onReady={() => undefined}
        onViewerAttach={attachViewer}
        networkProfile={CLASSROOM_VIEWER_NETWORK_PROFILE}
      />}
      <ClassroomPinOverlays pins={visiblePins} slideId={currentSlide?.id ?? ''} viewer={viewer} />
      <ClassroomTeachingOverlays
        ref={teachingOverlayRef}
        annotations={state?.teachingAnnotations ?? []}
        pointer={teachingTool === 'pointer' ? null : state?.teacherPointer ?? null}
        slideId={currentSlide?.id ?? ''}
        viewer={viewer}
      />
      {teachingTool === 'draw' ? <StudentDrawingOverlay
        key={currentSlide?.id ?? 'teaching-drawing'}
        active
        allowEraser
        retainCommitted={false}
        showHistoryActions={false}
        toolbarLabel="Teaching annotation tools"
        onStrokeCommitted={teachingAnnotation}
        onDone={() => setTeachingTool('navigate')}
      /> : null}
      <div className="classroom-teaching-tools" role="toolbar" aria-label="Live teaching tools">
        <button
          className={`classroom-guide-toggle${guideMode ? ' is-active' : ''}`}
          type="button"
          aria-pressed={guideMode}
          aria-label={guideMode ? 'Stop guiding students' : 'Guide students'}
          title={guideMode ? 'Guide mode on — students follow this view' : 'Guide mode off — navigation stays local'}
          onClick={() => {
            const next = !guideMode
            setGuideMode(next)
            if (next && viewer && currentSlide && !state?.controller.participantId) {
              void publishTeacherViewport(classroom.id, readPresenterViewport(viewer, currentSlide.id))
                .then(() => setError((current) => current === 'The live field could not be shared.' ? '' : current))
                .catch((caught: unknown) => {
                  handleAdminFailure(caught, 'The live field could not be shared.')
                })
            }
          }}
        ><TeachingToolIcon name="guide" /><span className="classroom-tool-status" aria-hidden="true" /></button>
        <span className="classroom-tool-separator" aria-hidden="true" />
        {([
          ['navigate', 'Navigate', 'navigate'],
          ['draw', 'Draw', 'draw'],
          ['pointer', 'Arrow pointer', 'arrow'],
        ] as const).map(([tool, label, icon]) => <button
          key={tool}
          className={`classroom-tool-${tool}${tool === 'pointer' ? ` is-${pointerColor}` : ''}${teachingTool === tool ? ' is-active' : ''}`}
          type="button"
          aria-pressed={teachingTool === tool}
          aria-label={label}
          title={label}
          disabled={tool !== 'navigate' && Boolean(state?.controller.participantId)}
          onClick={() => setTeachingTool(tool)}
        ><TeachingToolIcon name={icon} /></button>)}
      </div>
      {teachingTool === 'pointer' ? <div className="classroom-pointer-options" role="toolbar" aria-label="Pointer color">
        {(['green', 'red'] as const).map((color) => <button
          key={color}
          className={`is-${color}${pointerColor === color ? ' is-active' : ''}`}
          type="button"
          aria-label={`${color === 'green' ? 'Green' : 'Red'} pointer`}
          aria-pressed={pointerColor === color}
          title={`${color === 'green' ? 'Green' : 'Red'} pointer`}
          onClick={() => setPointerColor(color)}
        />)}
      </div> : null}
      <ClassroomSlideNavigator
        activeId={currentSlide?.id ?? ''}
        slides={classroom.slides}
        onSelect={(nextSlideId) => {
          setTeachingTool('navigate')
          setSlideId(nextSlideId)
        }}
      />
    </main>
    <aside className="classroom-panel" aria-label="Classroom activity">
      {error && <p role="alert" className="classroom-error">{error}</p>}
      <section className="classroom-panel__section">
        <h2><span className="classroom-panel__title"><ClassroomPanelIcon name="students" />Students</span><strong className="classroom-panel__count" aria-label={`${activeParticipantCount} students`}>{activeParticipantCount}</strong></h2>
        <label className="classroom-roster-search">
          <span>Search students</span>
          <input
            type="search"
            value={rosterQuery}
            onChange={(event) => setRosterQuery(event.target.value)}
            placeholder="Alias or name"
            autoComplete="off"
          />
        </label>
        {!rosterLoading && !participants.length && <p className="classroom-empty">
          {deferredRosterQuery ? 'No students match this search.' : 'Students appear here after joining.'}
        </p>}
        {rosterLoading && !participants.length ? <p className="classroom-empty" role="status">Loading students…</p> : null}
        <ul className="classroom-participant-list" aria-label="Student roster">{participants.map((participant) => {
          const isController = state?.controller.participantId === participant.id
          return <li key={participant.id}>
            <div>
              <strong>{participant.alias}</strong>
              <small>{participant.displayName ? `${participant.displayName} · ` : ''}{isController
                ? `${participant.status} · controller`
                : participant.controlRequested
                  ? `${participant.status} · requested control`
                  : participant.status}</small>
            </div>
            {isController || participant.controlRequested ? <button className="classroom-icon-action" type="button" aria-label={isController ? `Take back control from ${participant.alias}` : `Give control to ${participant.alias}`} title={isController ? 'Take back control' : 'Give control'} disabled={participant.status === 'disconnected'} onClick={() => void (isController
              ? revokeControl(classroom.id)
              : grantControl(classroom.id, participant.id)
            ).then(() => {
              if (!isController) {
                pendingControlRequest.current += 1
                setPendingControlLoading(false)
                setPinnedControlRequests((current) => current.filter(
                  (item) => item.id !== participant.id,
                ))
                setRoster((current) => {
                  const next = {
                    ...current,
                    items: current.items.map((item) => item.id === participant.id
                      ? { ...item, controlRequested: false, controlRequestedAt: null }
                      : item),
                  }
                  rosterRef.current = next
                  return next
                })
              }
              return refresh(classroom.id)
            }).catch(() => {
              setError('Slide control could not be changed.')
            })}>
              <ClassroomPanelIcon name="control" />
            </button> : null}
          </li>
        })}</ul>
        {pendingControlPage.nextCursor ? <button
          className="classroom-roster-more"
          type="button"
          disabled={pendingControlLoading}
          onClick={() => void loadMorePendingControlRequests(classroom.id).catch(() => {
            setError('More control requests could not be loaded.')
          })}
        >{pendingControlLoading
            ? 'Loading control requests…'
            : `Load more control requests (${pinnedControlRequests.length} of ${pendingControlPage.total})`}</button> : null}
        {roster.nextCursor ? <button
          className="classroom-roster-more"
          type="button"
          disabled={rosterLoading}
          onClick={() => void loadMoreRoster(classroom.id).catch(() => {
            setError('More students could not be loaded.')
          })}
        >{rosterLoading ? 'Loading…' : `Load more (${roster.items.length} of ${roster.total})`}</button> : null}
      </section>
      <section className="classroom-panel__section">
        <h2><span className="classroom-panel__title"><ClassroomPanelIcon name="questions" />Questions</span><strong className="classroom-panel__count" aria-label={`${state?.pendingQuestions.length ?? 0} pending questions`}>{state?.pendingQuestions.length ?? 0}</strong></h2>
        {!state?.pendingQuestions.length && <p className="classroom-empty">Pinned questions appear here.</p>}
        <ul className="classroom-question-list">{state?.pendingQuestions.map((question) => <li className="classroom-question-item" key={question.id}>
          <p>{question.text}</p>
          <div className="classroom-question-actions">
            <button className="classroom-icon-action" type="button" aria-label="Show pinned field" title="Show field" onClick={() => {
              setFocusedQuestion(question)
              void openQuestion(classroom.id, question.id).catch(() => {
                setError('The pinned field could not be opened.')
              })
            }}>
              <ClassroomPanelIcon name="locate" />
            </button>
            <button className="classroom-icon-action" type="button" aria-label="Mark question answered" title="Answered" onClick={() => void answerQuestion(classroom.id, question.id).then(() => {
              if (focusedQuestion?.id === question.id) setFocusedQuestion(null)
            })}>
              <ClassroomPanelIcon name="check" />
            </button>
          </div>
        </li>)}</ul>
      </section>
      <section className="classroom-panel__section">
        <h2><span className="classroom-panel__title"><ClassroomPanelIcon name="marks" />Teaching marks</span><strong className="classroom-panel__count">{state?.teachingAnnotations.length ?? 0}</strong></h2>
        {!state?.teachingAnnotations.length ? <p className="classroom-empty">Drawn marks appear to everyone in this session and disappear when class ends.</p> : <ul className="classroom-mark-history">
          {[...(state?.teachingAnnotations ?? [])].reverse().map((annotation, index) => <li key={annotation.id}>
            <span style={{ background: annotation.color }} />
            <div><strong>{annotation.tool === 'highlight' ? 'Highlight' : annotation.tool === 'line' ? 'Line' : annotation.tool === 'rectangle' ? 'Rectangle' : annotation.tool === 'ellipse' ? 'Ellipse' : 'Pen mark'}</strong><small>Mark {(state?.teachingAnnotations.length ?? 0) - index}</small></div>
            <button className="classroom-icon-action" type="button" aria-label={`Remove mark ${(state?.teachingAnnotations.length ?? 0) - index}`} title="Remove" onClick={() => void removeTeachingAnnotation(classroom.id, annotation.id)}><ClassroomPanelIcon name="remove" /></button>
          </li>)}
        </ul>}
        {state?.teachingAnnotations.length ? <button className="classroom-clear-marks" type="button" onClick={() => void clearTeachingAnnotations(classroom.id)}><ClassroomPanelIcon name="clear" />Clear all</button> : null}
      </section>
    </aside>
    {showCode && classroom.publicId ? <InviteDialog classroom={classroom} onClose={() => setShowCode(false)} /> : null}
  </div>
}
