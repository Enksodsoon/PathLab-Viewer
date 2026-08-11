import OpenSeadragon from 'openseadragon'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, listSlides } from '../api'
import {
  answerQuestion,
  clearTeacherPointer,
  clearTeachingAnnotations,
  createClassroom,
  endClassroom,
  grantControl,
  openQuestion,
  publishTeacherPointer,
  publishTeacherViewport,
  publishTeachingAnnotation,
  removeTeachingAnnotation,
  revokeControl,
  teacherState,
  type CreatedClassroom,
  type TeacherState,
  type TeachingAnnotation,
} from '../classroom/api'
import { ClassroomPinOverlays, type ClassroomVisiblePin } from '../classroom/ClassroomPinOverlays'
import { ClassroomSlideNavigator } from '../classroom/ClassroomSlideNavigator'
import { ClassroomTeachingOverlays } from '../classroom/ClassroomTeachingOverlays'
import { createLatestSender } from '../classroom/latestSender'
import { applyPresenterViewport, readPresenterViewport } from '../classroom/presenterViewport'
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
import type { AdminSlide } from '../types'
import '../classroom/classroom.css'

const ACTIVE_CLASSROOM_KEY = 'pathlab-active-classroom:v1'

function TeachingToolIcon({ name }: { name: 'guide' | 'navigate' | 'draw' | 'laser' | 'arrow' }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {name === 'guide' ? <><circle cx="12" cy="12" r="2" fill="currentColor" /><path d="M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.5 5.5a9.2 9.2 0 0 0 0 13M18.5 5.5a9.2 9.2 0 0 1 0 13" /></> : null}
    {name === 'navigate' ? <path d="m5 3 13.5 9-6.1 1.2L9.5 19 5 3Z" fill="currentColor" /> : null}
    {name === 'draw' ? <><path d="m4 20 4.2-1 10.4-10.4-3.2-3.2L5 15.8 4 20Z" /><path d="m13.8 7 3.2 3.2" /></> : null}
    {name === 'laser' ? <><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2" fill="currentColor" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></> : null}
    {name === 'arrow' ? <><path d="M5 19 19 5M10 5h9v9" /><path d="M5 19h5" /></> : null}
  </svg>
}

function savedClassroom(): CreatedClassroom | null {
  try {
    const value = sessionStorage.getItem(ACTIVE_CLASSROOM_KEY)
    return value ? JSON.parse(value) as CreatedClassroom : null
  } catch {
    return null
  }
}

export function ClassroomTeacherPage() {
  const navigate = useNavigate()
  const [slides, setSlides] = useState<AdminSlide[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [classroom, setClassroom] = useState<CreatedClassroom | null>(savedClassroom)
  const [state, setState] = useState<TeacherState | null>(null)
  const [slideId, setSlideId] = useState('')
  const [error, setError] = useState('')
  const [showCode, setShowCode] = useState(false)
  const [focusedQuestion, setFocusedQuestion] = useState<TeacherState['pendingQuestions'][number] | null>(null)
  const [viewer, setViewer] = useState<OpenSeadragon.Viewer | null>(null)
  const [teachingTool, setTeachingTool] = useState<'navigate' | 'draw' | 'laser' | 'green-arrow' | 'red-arrow'>('navigate')
  const [guideMode, setGuideMode] = useState(false)
  const suppressPublish = useRef(false)
  const stateRef = useRef<TeacherState | null>(null)
  const presenterRef = useRef<TeacherState['presenter'] | null>(null)
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)
  const slideIdRef = useRef(slideId)
  const streamEpoch = useRef('')
  const streamSequence = useRef(0)
  const teachingToolRef = useRef(teachingTool)
  const guideModeRef = useRef(guideMode)

  useEffect(() => { stateRef.current = state }, [state])
  useEffect(() => { slideIdRef.current = slideId }, [slideId])
  useEffect(() => { teachingToolRef.current = teachingTool }, [teachingTool])
  useEffect(() => { guideModeRef.current = guideMode }, [guideMode])
  useEffect(() => {
    if (!showCode) return
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setShowCode(false)
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [showCode])

  useEffect(() => {
    void listSlides()
      .then((items) => setSlides(items.filter((slide) => (
        slide.state === 'published' && slide.renderMode === 'static_dzi'
      ))))
      .catch((loadError: unknown) => {
        if (loadError instanceof ApiError && loadError.status === 401) {
          navigate('/admin', { replace: true })
          return
        }
        setError('Published slides could not be loaded.')
      })
  }, [navigate])

  const refresh = useCallback(async (sessionId: string) => {
    const next = await teacherState(sessionId)
    presenterRef.current = next.presenter
    setState(next)
    if (next.presenter.slideId) setSlideId(next.presenter.slideId)
  }, [])

  useEffect(() => {
    if (!classroom) return
    void refresh(classroom.id).catch((loadError: unknown) => {
      if (loadError instanceof ApiError && loadError.status === 404) {
        sessionStorage.removeItem(ACTIVE_CLASSROOM_KEY)
        setClassroom(null)
        setError('The previous classroom is no longer active.')
        return
      }
      setError('The classroom connection was interrupted. Reconnecting…')
    })
    const events = new EventSource(`/api/v1/admin/classroom/sessions/${classroom.id}/events`)
    const sequence = (event: Event, coalescible = false): Record<string, unknown> | null => {
      try {
        const payload = JSON.parse((event as MessageEvent<string>).data) as Record<string, unknown>
        const epoch = typeof payload.hubEpoch === 'string' ? payload.hubEpoch : ''
        const next = typeof payload.eventSequence === 'number' ? payload.eventSequence : 0
        if (event.type === 'stream-ready') {
          streamEpoch.current = epoch
          streamSequence.current = next
          return payload
        }
        if (epoch === streamEpoch.current && next <= streamSequence.current) return null
        if (epoch !== streamEpoch.current || (!coalescible && next !== streamSequence.current + 1)) {
          streamEpoch.current = epoch
          streamSequence.current = next
          void refresh(classroom.id).catch(() => undefined)
          return null
        }
        streamSequence.current = next
        return payload
      } catch {
        void refresh(classroom.id).catch(() => undefined)
        return null
      }
    }
    const update = (event: Event) => {
      if (sequence(event)) void refresh(classroom.id).catch(() => undefined)
    }
    for (const name of [
      'stream-ready', 'participant-joined', 'participant-left',
      'participant-reconnected', 'question-added', 'question-removed', 'control',
    ]) events.addEventListener(name, update)
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
      setState((current) => current ? {
        ...current,
        teacherPointer: payload as unknown as TeacherState['teacherPointer'],
      } : current)
    })
    events.addEventListener('pointer-removed', (event) => {
      if (!sequence(event)) return
      setState((current) => current ? { ...current, teacherPointer: null } : current)
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
    events.addEventListener('control-requested', update)
    events.addEventListener('control-request-cancelled', update)
    return () => events.close()
  }, [classroom, refresh])

  const currentSlide = useMemo(
    () => classroom?.slides.find((slide) => slide.id === slideId) ?? classroom?.slides[0],
    [classroom, slideId],
  )

  const participants = useMemo(() => [...(state?.participants ?? [])].sort((left, right) => {
    if (left.controlRequested !== right.controlRequested) return left.controlRequested ? -1 : 1
    return (left.controlRequestedAt ?? Number.POSITIVE_INFINITY)
      - (right.controlRequestedAt ?? Number.POSITIVE_INFINITY)
  }), [state?.participants])

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
    viewer?.setMouseNavEnabled(teachingTool === 'navigate')
    if (!classroom || teachingTool === 'laser'
      || teachingTool === 'green-arrow' || teachingTool === 'red-arrow') return
    void clearTeacherPointer(classroom.id).catch(() => undefined)
  }, [classroom, teachingTool, viewer])

  const teachingAnnotation = useCallback((stroke: DrawingStroke) => {
    if (!viewer || !currentSlide || !classroom || stroke.tool === 'eraser') return
    const item = viewer.world.getItemAt(0)
    if (!item) return
    const bounds = viewer.container.getBoundingClientRect()
    const dimensions = item.source.dimensions
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
    void publishTeachingAnnotation(classroom.id, annotation).catch(() => {
      setError('The teaching mark could not be shared.')
    })
  }, [classroom, currentSlide, viewer])

  const attachViewer = useCallback<ViewerAttachmentCallback>((viewer) => {
    viewerRef.current = viewer
    setViewer(viewer)
    const sender = createLatestSender((payload: ReturnType<typeof readPresenterViewport>) => (
      publishTeacherViewport(classroom!.id, payload).catch(() => {
        setError('The live field could not be shared.')
      })
    ))
    const publish = () => {
      if (suppressPublish.current) {
        suppressPublish.current = false
        return
      }
      if (!guideModeRef.current || stateRef.current?.controller.participantId
        || !classroom || !currentSlide) return
      sender.push(readPresenterViewport(viewer, currentSlide.id))
    }
    const opened = () => applyRemote(viewer)
    let pointerVisible = false
    const pointerSender = createLatestSender((pointer: Parameters<typeof publishTeacherPointer>[1]) => {
      pointerVisible = true
      return publishTeacherPointer(classroom!.id, pointer).catch(() => {
        setError('The live pointer could not be shared.')
      })
    }, 100)
    const point = (event: globalThis.PointerEvent) => {
      const style = teachingToolRef.current
      if (!classroom || !currentSlide || (style !== 'laser'
        && style !== 'green-arrow' && style !== 'red-arrow')) return
      const item = viewer.world.getItemAt(0)
      if (!item) return
      const bounds = viewer.canvas.getBoundingClientRect()
      const viewportPoint = viewer.viewport.pointFromPixel(new OpenSeadragon.Point(
        event.clientX - bounds.left,
        event.clientY - bounds.top,
      ), true)
      const imagePoint = viewer.viewport.viewportToImageCoordinates(viewportPoint)
      const dimensions = item.source.dimensions
      pointerSender.push({
        slideId: currentSlide.id,
        style,
        x: Math.max(0, Math.min(1, imagePoint.x / dimensions.x)),
        y: Math.max(0, Math.min(1, imagePoint.y / dimensions.y)),
      })
    }
    const clearPointer = () => {
      if (!classroom || !pointerVisible) return
      pointerVisible = false
      void clearTeacherPointer(classroom.id).catch(() => undefined)
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
      sender.dispose()
      pointerSender.dispose()
      clearPointer()
      if (viewerRef.current === viewer) viewerRef.current = null
      setViewer(null)
    }
  }, [applyRemote, classroom, currentSlide])

  const start = async () => {
    setError('')
    try {
      const created = await createClassroom(selected)
      setClassroom(created)
      sessionStorage.setItem(ACTIVE_CLASSROOM_KEY, JSON.stringify(created))
      setSlideId(created.slides[0].id)
    } catch (startError) {
      if (startError instanceof ApiError && startError.code === 'CLASSROOM_ALREADY_ACTIVE') {
        setError('A classroom is already active. End it before starting another.')
      } else if (startError instanceof ApiError && startError.code === 'CLASSROOM_SLIDE_NOT_READY') {
        setError('The classroom could not start. Only complete published static slides are allowed.')
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
        <Link className="classroom-back-link" to="/admin">Back to library</Link>
      </div>
    </header>
    <section className="classroom-entry__card">
      <p className="classroom-kicker">Active classroom</p>
      <h1>Choose teaching slides</h1>
      <p className="classroom-entry__intro">Only the selected published DZI versions are pinned for this session.</p>
      {error && <p role="alert" className="classroom-error">{error}</p>}
      <div className="classroom-slide-picker">
        {slides.map((slide) => <label key={slide.id}>
          <input
            type="checkbox"
            checked={selected.includes(slide.id)}
            onChange={(event) => setSelected((current) => event.target.checked
              ? [...current, slide.id]
              : current.filter((id) => id !== slide.id))}
          />
          <span>{slide.displayName}</span>
        </label>)}
      </div>
      <button className="primary classroom-entry__primary" type="button" disabled={!selected.length} onClick={() => void start()}>
        Start classroom
      </button>
    </section>
  </main>

  return <div className="classroom-shell classroom-shell--teacher">
    <header className="classroom-topbar">
      <Brand variant="library" />
      <button className="classroom-join-code" type="button" onClick={() => setShowCode(true)}>
        <span>Join code</span><strong>{classroom.joinCode}</strong><small>Display</small>
      </button>
      <div className="classroom-topbar__actions">
        <ThemeControl compact />
        <button className="classroom-danger-action" type="button" onClick={() => void endClassroom(classroom.id).then(() => {
          sessionStorage.removeItem(ACTIVE_CLASSROOM_KEY)
          setClassroom(null)
        })}>
          End class
        </button>
      </div>
    </header>
    <main className="classroom-viewer">
      {currentSlide && <OpenSeadragonViewer
        tileSource={currentSlide.tileSource}
        onReady={() => undefined}
        onViewerAttach={attachViewer}
      />}
      <ClassroomPinOverlays pins={visiblePins} slideId={currentSlide?.id ?? ''} viewer={viewer} />
      <ClassroomTeachingOverlays
        annotations={state?.teachingAnnotations ?? []}
        pointer={state?.teacherPointer ?? null}
        slideId={currentSlide?.id ?? ''}
        viewer={viewer}
      />
      {teachingTool === 'draw' ? <StudentDrawingOverlay
        key={currentSlide?.id ?? 'teaching-drawing'}
        active
        allowEraser={false}
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
            }
          }}
        ><TeachingToolIcon name="guide" /><span>{guideMode ? 'Live' : 'Guide'}</span></button>
        <span className="classroom-tool-separator" aria-hidden="true" />
        {([
          ['navigate', 'Navigate', 'navigate'],
          ['draw', 'Draw', 'draw'],
          ['laser', 'Laser pointer', 'laser'],
          ['green-arrow', 'Green arrow', 'arrow'],
          ['red-arrow', 'Red arrow', 'arrow'],
        ] as const).map(([tool, label, icon]) => <button
          key={tool}
          className={`classroom-tool-${tool}${teachingTool === tool ? ' is-active' : ''}`}
          type="button"
          aria-pressed={teachingTool === tool}
          aria-label={label}
          title={label}
          disabled={tool !== 'navigate' && Boolean(state?.controller.participantId)}
          onClick={() => setTeachingTool(tool)}
        ><TeachingToolIcon name={icon} /></button>)}
      </div>
      <ClassroomSlideNavigator
        activeId={currentSlide?.id ?? ''}
        slides={classroom.slides}
        onSelect={(nextSlideId) => {
          setTeachingTool('navigate')
          setSlideId(nextSlideId)
        }}
      />
    </main>
    <aside className="classroom-panel">
      {error && <p role="alert" className="classroom-error">{error}</p>}
      <section>
        <h2>Students <span>{state?.participants.length ?? 0}/300</span></h2>
        {!state?.participants.length && <p className="classroom-empty">Students appear here after joining.</p>}
        <ul className="classroom-participant-list">{participants.map((participant) => {
          const isController = state?.controller.participantId === participant.id
          return <li key={participant.id}>
            <div>
              <strong>{participant.alias}</strong>
              <small>{isController
                ? `${participant.status} · controller`
                : participant.controlRequested
                  ? `${participant.status} · requested control`
                  : participant.status}</small>
            </div>
            {isController || participant.controlRequested ? <button type="button" disabled={participant.status === 'disconnected'} onClick={() => void (isController
              ? revokeControl(classroom.id)
              : grantControl(classroom.id, participant.id)
            ).then(() => refresh(classroom.id)).catch(() => {
              setError('Slide control could not be changed.')
            })}>
              {isController ? 'Take back control' : 'Give control'}
            </button> : null}
          </li>
        })}</ul>
      </section>
      <section>
        <h2>Questions <span>{state?.pendingQuestions.length ?? 0}/200</span></h2>
        {!state?.pendingQuestions.length && <p className="classroom-empty">Pinned questions appear here.</p>}
        <ul className="classroom-question-list">{state?.pendingQuestions.map((question) => <li className="classroom-question-item" key={question.id}>
          <p>{question.text}</p>
          <div className="classroom-question-actions">
            <button type="button" onClick={() => {
              setFocusedQuestion(question)
              void openQuestion(classroom.id, question.id).catch(() => {
                setError('The pinned field could not be opened.')
              })
            }}>
              Show field
            </button>
            <button type="button" onClick={() => void answerQuestion(classroom.id, question.id).then(() => {
              if (focusedQuestion?.id === question.id) setFocusedQuestion(null)
            })}>
              Answered
            </button>
          </div>
        </li>)}</ul>
      </section>
      <section>
        <h2>Teaching marks <span>{state?.teachingAnnotations.length ?? 0}/40</span></h2>
        {!state?.teachingAnnotations.length ? <p className="classroom-empty">Drawn marks appear to everyone in this session and disappear when class ends.</p> : <ul className="classroom-mark-history">
          {[...(state?.teachingAnnotations ?? [])].reverse().map((annotation, index) => <li key={annotation.id}>
            <span style={{ background: annotation.color }} />
            <div><strong>{annotation.tool === 'highlight' ? 'Highlight' : 'Pen mark'}</strong><small>Mark {(state?.teachingAnnotations.length ?? 0) - index}</small></div>
            <button type="button" onClick={() => void removeTeachingAnnotation(classroom.id, annotation.id)}>Remove</button>
          </li>)}
        </ul>}
        {state?.teachingAnnotations.length ? <button type="button" onClick={() => void clearTeachingAnnotations(classroom.id)}>Clear teaching marks</button> : null}
      </section>
    </aside>
    {showCode ? <div className="classroom-code-display" role="dialog" aria-modal="true" aria-labelledby="classroom-code-title">
      <div>
        <p>PathLab classroom</p>
        <h2 id="classroom-code-title">Join this slide session</h2>
        <strong>{classroom.joinCode}</strong>
        <span>Open PathLab Classroom and enter this code</span>
        <button type="button" autoFocus onClick={() => setShowCode(false)}>Close</button>
      </div>
    </div> : null}
  </div>
}
