import OpenSeadragon from 'openseadragon'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import {
  cancelControlRequest,
  clearPin,
  joinClassroom,
  publishPin,
  publishStudentViewport,
  requestControl,
  studentState,
  submitQuestion,
  type StudentState,
} from '../classroom/api'
import { ClassroomPinOverlays } from '../classroom/ClassroomPinOverlays'
import { ClassroomSlideNavigator } from '../classroom/ClassroomSlideNavigator'
import { ClassroomTeachingOverlays } from '../classroom/ClassroomTeachingOverlays'
import { createLatestSender } from '../classroom/latestSender'
import { applyPresenterViewport, readPresenterViewport } from '../classroom/presenterViewport'
import {
  StudentDrawingOverlay,
  type StudentDrawingHandle,
} from '../classroom/StudentDrawingOverlay'
import {
  deleteSessionEntries,
  listEntries,
  notebookFile,
  notebookHtml,
  saveEntry,
  storageCapability,
  type NotebookEntry,
  type StorageCapability,
} from '../classroom/notebook'
import { captureVisibleTissue } from '../classroom/screenshot'
import { classroomReconnectDelay } from '../classroom/reconnect'
import { Brand } from '../components/Brand'
import {
  OpenSeadragonViewer,
  type ViewerAttachmentCallback,
} from '../components/OpenSeadragonViewer'
import { ThemeControl } from '../theme/ThemeControl'
import '../classroom/classroom.css'

interface Pin {
  slideId: string
  x: number
  y: number
  zoom: number
}

function normalizedViewport(viewer: OpenSeadragon.Viewer, slideId: string) {
  const center = viewer.viewport.viewportToImageCoordinates(viewer.viewport.getCenter(true))
  const dimensions = viewer.world.getItemAt(0)?.source.dimensions
  return {
    slideId,
    x: dimensions ? center.x / dimensions.x : 0.5,
    y: dimensions ? center.y / dimensions.y : 0.5,
    zoom: viewer.viewport.getZoom(true),
  }
}

function largestCanvas(viewer: OpenSeadragon.Viewer): HTMLCanvasElement | null {
  return [...viewer.container.querySelectorAll<HTMLCanvasElement>('canvas')]
    .sort((left, right) => right.width * right.height - left.width * left.height)[0] ?? null
}

export function ClassroomStudentPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const [joinCode, setJoinCode] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [alias, setAlias] = useState('')
  const [state, setState] = useState<StudentState | null>(null)
  const [follow, setFollow] = useState(true)
  const [slideId, setSlideId] = useState('')
  const [pinMode, setPinMode] = useState(false)
  const [pinTarget, setPinTarget] = useState<{ x: number; y: number } | null>(null)
  const [pin, setPin] = useState<Pin | null>(null)
  const [question, setQuestion] = useState('')
  const [note, setNote] = useState('')
  const [entries, setEntries] = useState<NotebookEntry[]>([])
  const [storage, setStorage] = useState<StorageCapability>({ indexedDb: false })
  const [message, setMessage] = useState('')
  const [drawing, setDrawing] = useState(false)
  const [viewer, setViewer] = useState<OpenSeadragon.Viewer | null>(null)
  const drawingRef = useRef<StudentDrawingHandle | null>(null)
  const drawingModeRef = useRef(false)
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)
  const suppressPublish = useRef(false)
  const followRef = useRef(follow)
  const stateRef = useRef<StudentState | null>(null)
  const presenterRef = useRef<StudentState['presenter'] | null>(null)
  const slideIdRef = useRef(slideId)
  const csrfRef = useRef(csrfToken)
  const streamEpoch = useRef('')
  const streamSequence = useRef(0)
  const wasController = useRef(false)

  useEffect(() => { stateRef.current = state }, [state])
  useEffect(() => { followRef.current = follow }, [follow])
  useEffect(() => { slideIdRef.current = slideId }, [slideId])
  useEffect(() => { csrfRef.current = csrfToken }, [csrfToken])
  useEffect(() => {
    const isController = state?.control.isController ?? false
    if (isController) setFollow(false)
    else if (wasController.current) setFollow(true)
    wasController.current = isController
  }, [state?.control.isController])
  useEffect(() => { void storageCapability().then(setStorage) }, [])
  useEffect(() => {
    if (!sessionId || csrfToken) return
    void studentState(sessionId).then(async (next) => {
      presenterRef.current = next.presenter
      setState(next)
      setCsrfToken(next.csrfToken)
      setAlias(next.participant.alias)
      setPin(next.activePin)
      if (next.presenter.slideId) setSlideId(next.presenter.slideId)
      setEntries(await listEntries(sessionId))
    }).catch(() => setMessage('Rejoin with the classroom code to continue.'))
  }, [csrfToken, sessionId])

  const refresh = useCallback(async (id: string) => {
    const next = await studentState(id)
    presenterRef.current = next.presenter
    setState(next)
    setPin(next.activePin)
    if (follow && !drawingModeRef.current && next.presenter.slideId) setSlideId(next.presenter.slideId)
    setEntries(await listEntries(id))
  }, [follow])

  useEffect(() => {
    const participantId = state?.participant.id
    if (!sessionId || !csrfToken || !participantId) return
    void refresh(sessionId)
    let events: EventSource | null = null
    let retryTimer: number | null = null
    let stableTimer: number | null = null
    let attempt = 0
    let cancelled = false
    const recover = () => { void refresh(sessionId).catch(() => undefined) }
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
          recover()
          return null
        }
        streamSequence.current = next
        return payload
      } catch {
        recover()
        return null
      }
    }
    const connect = () => {
      if (cancelled) return
      const source = new EventSource(`/api/v1/classroom/sessions/${sessionId}/events`)
      events = source
      source.addEventListener('stream-ready', (event) => {
        sequence(event)
        recover()
        if (stableTimer !== null) window.clearTimeout(stableTimer)
        stableTimer = window.setTimeout(() => { attempt = 0 }, 5000)
      })
      source.addEventListener('presenter', (event) => {
        const payload = sequence(event, true)
        if (!payload || typeof payload.presenterSequence !== 'number'
          || typeof payload.slideId !== 'string' || !payload.viewport) return
        const nextPresenter: StudentState['presenter'] = {
          sequence: payload.presenterSequence as number,
          slideId: payload.slideId as string,
          viewport: payload.viewport as StudentState['presenter']['viewport'],
        }
        presenterRef.current = nextPresenter
        if (!followRef.current || drawingModeRef.current) return
        if (slideIdRef.current !== nextPresenter.slideId) {
          slideIdRef.current = nextPresenter.slideId ?? ''
          setSlideId(nextPresenter.slideId ?? '')
          return
        }
        const target = viewerRef.current
        const slide = stateRef.current?.slides.find((item) => item.id === nextPresenter.slideId)
        if (!target || !slide || !nextPresenter.viewport) return
        suppressPublish.current = true
        applyPresenterViewport(target, slide, nextPresenter.viewport)
        window.setTimeout(() => { suppressPublish.current = false }, 0)
      })
      source.addEventListener('control', (event) => { if (sequence(event)) recover() })
      source.addEventListener('pointer', (event) => {
        const payload = sequence(event, true)
        if (!payload || typeof payload.slideId !== 'string'
          || typeof payload.style !== 'string' || typeof payload.x !== 'number'
          || typeof payload.y !== 'number') return
        setState((current) => current ? {
          ...current,
          teacherPointer: payload as unknown as StudentState['teacherPointer'],
        } : current)
      })
      source.addEventListener('pointer-removed', (event) => {
        if (!sequence(event)) return
        setState((current) => current ? { ...current, teacherPointer: null } : current)
      })
      source.addEventListener('teaching-annotation-added', (event) => {
        const payload = sequence(event)
        const annotation = payload?.annotation as StudentState['teachingAnnotations'][number] | undefined
        if (!annotation?.id) return
        setState((current) => current ? {
          ...current,
          teachingAnnotations: [
            ...(current.teachingAnnotations ?? []).filter((item) => item.id !== annotation.id),
            annotation,
          ].slice(-40),
        } : current)
      })
      source.addEventListener('teaching-annotation-removed', (event) => {
        const payload = sequence(event)
        if (!payload || typeof payload.annotationId !== 'string') return
        setState((current) => current ? {
          ...current,
          teachingAnnotations: (current.teachingAnnotations ?? []).filter(
            (item) => item.id !== payload.annotationId,
          ),
        } : current)
      })
      source.addEventListener('teaching-annotations-cleared', (event) => {
        if (!sequence(event)) return
        setState((current) => current ? { ...current, teachingAnnotations: [] } : current)
      })
      source.addEventListener('session-ended', (event) => {
        if (!sequence(event)) return
        setState(null)
        setCsrfToken('')
        setMessage('This classroom has ended.')
        navigate('/classroom', { replace: true })
      })
      source.addEventListener('question-removed', (event) => {
        const payload = sequence(event)
        if (!payload || typeof payload.questionId !== 'string') return
        setState((current) => current ? {
          ...current,
          pendingQuestionIds: current.pendingQuestionIds.filter(
            (questionId) => questionId !== payload.questionId,
          ),
        } : current)
      })
      source.addEventListener('error', () => {
        source.close()
        if (events === source) events = null
        if (cancelled || retryTimer !== null) return
        if (stableTimer !== null) window.clearTimeout(stableTimer)
        retryTimer = window.setTimeout(() => {
          retryTimer = null
          attempt += 1
          connect()
        }, classroomReconnectDelay(participantId, attempt))
      })
    }
    connect()
    return () => {
      cancelled = true
      events?.close()
      if (retryTimer !== null) window.clearTimeout(retryTimer)
      if (stableTimer !== null) window.clearTimeout(stableTimer)
    }
  }, [csrfToken, navigate, refresh, sessionId, state?.participant.id])

  const currentSlide = useMemo(
    () => state?.slides.find((slide) => slide.id === slideId) ?? state?.slides[0],
    [slideId, state],
  )

  const applyRemote = useCallback((viewer: OpenSeadragon.Viewer) => {
    const current = stateRef.current
    const presenter = presenterRef.current
    const slide = current?.slides.find((item) => item.id === slideIdRef.current)
    if (drawingModeRef.current || !follow || !presenter?.viewport
      || presenter.slideId !== slide?.id || !slide) return
    suppressPublish.current = true
    applyPresenterViewport(viewer, slide, presenter.viewport)
    window.setTimeout(() => { suppressPublish.current = false }, 0)
  }, [follow])

  useEffect(() => {
    if (viewerRef.current) applyRemote(viewerRef.current)
  }, [applyRemote, state])

  useEffect(() => {
    drawingModeRef.current = drawing
    const target = viewerRef.current
    target?.setMouseNavEnabled(!drawing)
    if (!drawing && target && followRef.current) applyRemote(target)
  }, [applyRemote, drawing])

  const attachViewer = useCallback<ViewerAttachmentCallback>((viewer) => {
    viewerRef.current = viewer
    setViewer(viewer)
    const sender = createLatestSender((payload: ReturnType<typeof readPresenterViewport>) => {
      const current = stateRef.current
      if (!current?.control.leaseId || !sessionId) return Promise.resolve()
      return publishStudentViewport(
        sessionId,
        csrfRef.current,
        current.control.leaseId,
        payload,
      ).catch(() => setMessage('Slide control returned to the teacher.'))
    })
    const opened = () => applyRemote(viewer)
    const moved = () => {
      const current = stateRef.current
      if (drawingModeRef.current || suppressPublish.current || !current?.control.isController
        || !current.control.leaseId || !sessionId) return
      sender.push(readPresenterViewport(viewer, slideIdRef.current))
    }
    const clicked = (event: { position: OpenSeadragon.Point }) => {
      if (drawingModeRef.current || !pinMode || !currentSlide) return
      const image = viewer.viewport.viewportToImageCoordinates(
        viewer.viewport.pointFromPixel(event.position, true),
      )
      const nextPin = {
        slideId: currentSlide.id,
        x: Math.max(0, Math.min(1, image.x / currentSlide.width)),
        y: Math.max(0, Math.min(1, image.y / currentSlide.height)),
        zoom: viewer.viewport.getZoom(true),
      }
      setPin(nextPin)
      setPinMode(false)
      setPinTarget(null)
      if (sessionId) {
        void publishPin(sessionId, csrfRef.current, {
          slideId: currentSlide.id,
          x: nextPin.x,
          y: nextPin.y,
          zoom: nextPin.zoom,
        }).catch(() => setMessage('The teacher could not receive this pin.'))
      }
    }
    let pinFrame: number | null = null
    const trackPin = (event: globalThis.PointerEvent) => {
      if (!pinMode || drawingModeRef.current) return
      if (pinFrame !== null) window.cancelAnimationFrame(pinFrame)
      pinFrame = window.requestAnimationFrame(() => {
        pinFrame = null
        setPinTarget({ x: event.clientX, y: event.clientY })
      })
    }
    const hidePinTarget = () => setPinTarget(null)
    viewer.canvas.addEventListener('pointermove', trackPin)
    viewer.canvas.addEventListener('pointerleave', hidePinTarget)
    viewer.addHandler('open', opened)
    viewer.addHandler('animation', moved)
    viewer.addHandler('animation-finish', moved)
    viewer.addHandler('canvas-click', clicked)
    return () => {
      viewer.removeHandler('open', opened)
      viewer.removeHandler('animation', moved)
      viewer.removeHandler('animation-finish', moved)
      viewer.removeHandler('canvas-click', clicked)
      viewer.canvas.removeEventListener('pointermove', trackPin)
      viewer.canvas.removeEventListener('pointerleave', hidePinTarget)
      if (pinFrame !== null) window.cancelAnimationFrame(pinFrame)
      sender.dispose()
      viewerRef.current = null
      setViewer(null)
    }
  }, [applyRemote, currentSlide, pinMode, sessionId])

  const join = async () => {
    setMessage('')
    try {
      const joined = await joinClassroom(joinCode.trim().toUpperCase(), displayName)
      const next = await studentState(joined.sessionId)
      setState(next)
      setCsrfToken(next.csrfToken)
      setAlias(next.participant.alias)
      setPin(next.activePin)
      if (next.presenter.slideId) setSlideId(next.presenter.slideId)
      setEntries(await listEntries(joined.sessionId))
      navigate(`/classroom/${joined.sessionId}`, { replace: true })
    } catch {
      setMessage('That classroom is unavailable or the code is incorrect.')
    }
  }

  const ask = async () => {
    if (!sessionId || !currentSlide || !pin || !question.trim()) return
    await submitQuestion(sessionId, csrfToken, {
      slideId: currentSlide.id,
      text: question.trim(),
      x: pin.x,
      y: pin.y,
      zoom: pin.zoom,
    })
    setQuestion('')
    setPin(null)
    setMessage('Question sent to the teacher.')
  }

  const toggleControlRequest = async () => {
    if (!sessionId || !state || state.control.isController) return
    const requested = state.control.requested
    try {
      if (requested) await cancelControlRequest(sessionId, csrfToken)
      else await requestControl(sessionId, csrfToken)
      setState((current) => current ? {
        ...current,
        control: { ...current.control, requested: !requested },
      } : current)
      setMessage(requested ? 'Control request cancelled.' : 'The teacher has received your control request.')
    } catch {
      setMessage('The control request could not be changed.')
    }
  }

  const removePin = async () => {
    if (!sessionId) return
    setPin(null)
    setPinMode(false)
    try {
      await clearPin(sessionId, csrfToken)
    } catch {
      setMessage('The pin could not be cleared for the teacher.')
    }
  }

  const capture = async () => {
    if (!sessionId || !currentSlide || !viewerRef.current) return
    let image: Blob | undefined
    try {
      const canvas = largestCanvas(viewerRef.current)
      if (!canvas) throw new Error('The tissue view is not ready')
      image = (await captureVisibleTissue(
        canvas,
        drawingRef.current?.captureCanvas(),
      )).blob
    } catch (error) {
      if (!note.trim()) {
        setMessage(error instanceof Error ? error.message : 'Screenshot failed.')
        return
      }
      setMessage('Screenshot failed, but the text note was preserved.')
    }
    const field = normalizedViewport(viewerRef.current, currentSlide.id)
    const entry: NotebookEntry = {
      id: crypto.randomUUID(),
      sessionId,
      slideId: currentSlide.id,
      slideName: currentSlide.displayName,
      note: note.trim(),
      createdAt: new Date().toISOString(),
      image,
      viewport: { x: field.x, y: field.y, zoom: field.zoom },
      hasDrawing: drawingRef.current?.hasDrawing() ?? false,
    }
    await saveEntry(entry)
    setEntries((current) => [...current, entry])
    setNote('')
    drawingRef.current?.clear()
    setDrawing(false)
    if (image) setMessage('Screenshot and note saved on this device only.')
  }

  const downloadLocal = (file: File) => {
    const url = URL.createObjectURL(file)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = file.name
    anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  const shareLocal = async () => {
    const file = await notebookFile('PathLab classroom notebook', entries)
    if (navigator.share && navigator.canShare?.({ files: [file] })) {
      try {
        await navigator.share({
          title: 'PathLab classroom notebook',
          text: 'My private PathLab field notes',
          files: [file],
        })
        return
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return
      }
    }
    downloadLocal(file)
    setMessage('Notebook exported as an offline file.')
  }

  const printLocal = async () => {
    const preview = window.open('', '_blank')
    if (!preview) {
      setMessage('Allow pop-ups to print or save this notebook as PDF.')
      return
    }
    preview.document.open()
    preview.document.write(await notebookHtml('PathLab classroom notebook', entries))
    preview.document.close()
    preview.focus()
    window.setTimeout(() => preview.print(), 250)
  }

  if (!sessionId || !csrfToken) return <main className="classroom-entry classroom-join">
    <header className="classroom-entry__header">
      <Brand variant="library" />
      <ThemeControl compact />
    </header>
    <section className="classroom-entry__card">
      <p className="classroom-kicker">PathLab classroom</p>
      <h1>Join a slide session</h1>
      <p className="classroom-entry__intro">Enter the code shared by your teacher. Your generated alias is used in class.</p>
      <label><span>Join code</span><input autoCapitalize="characters" autoComplete="off" value={joinCode} maxLength={16} onChange={(event) => setJoinCode(event.target.value)} /></label>
      <label><span>Name <small>(optional)</small></span><input autoComplete="off" value={displayName} maxLength={80} onChange={(event) => setDisplayName(event.target.value)} /></label>
      <button className="primary classroom-entry__primary" type="button" disabled={joinCode.length < 6} onClick={() => void join()}>Join classroom</button>
      {message && <p className="classroom-message" role="status">{message}</p>}
    </section>
  </main>

  const isController = state?.control.isController ?? false
  const controlRequested = state?.control.requested ?? false

  return <div className="classroom-shell classroom-shell--student">
    <header className="classroom-topbar">
      <Brand variant="library" />
      <div className="classroom-learner-identity">
        <strong>{alias || 'Private learner'}</strong>
        <span className="classroom-control-status" role="status">
          {drawing ? 'View frozen for private drawing' : isController ? 'You control the slide' : 'Teacher controls the slide'}
        </span>
      </div>
      <div className="classroom-topbar__actions">
        <ThemeControl compact />
        <label className="classroom-follow-control"><input
          type="checkbox"
          checked={follow}
          disabled={isController}
          onChange={(event) => setFollow(event.target.checked)}
        /> <span>Follow teacher</span></label>
      </div>
    </header>
    <main className={`classroom-viewer${pinMode ? ' is-pin-mode' : ''}`}>
      {currentSlide && <OpenSeadragonViewer
        tileSource={currentSlide.tileSource}
        onReady={() => undefined}
        onViewerAttach={attachViewer}
      />}
      <ClassroomPinOverlays
        pins={pin ? [{
          participantId: state?.participant.id ?? 'student',
          alias: alias || 'Your pin',
          slideId: pin.slideId,
          x: pin.x,
          y: pin.y,
          focused: true,
        }] : []}
        slideId={currentSlide?.id ?? ''}
        viewer={viewer}
      />
      <ClassroomTeachingOverlays
        annotations={state?.teachingAnnotations ?? []}
        pointer={state?.teacherPointer ?? null}
        slideId={currentSlide?.id ?? ''}
        viewer={viewer}
      />
      {pinMode && pinTarget ? <div
        className="classroom-pin-target"
        style={{ left: pinTarget.x, top: pinTarget.y }}
        aria-hidden="true"
      ><span /><i /></div> : null}
      <StudentDrawingOverlay
        ref={drawingRef}
        active={drawing}
        onDone={() => setDrawing(false)}
      />
      <ClassroomSlideNavigator
        activeId={currentSlide?.id ?? ''}
        slides={state?.slides ?? []}
        onSelect={(nextSlideId) => {
          if (drawingRef.current?.hasDrawing()) {
            setMessage('Save or clear your private drawing before changing slides.')
            return
          }
          setFollow(false)
          setSlideId(nextSlideId)
          if (pin) void removePin()
        }}
      />
    </main>
    <aside className="classroom-panel">
      <section className="classroom-control-request">
        <div>
          <h2>Slide control</h2>
          <p>{isController
            ? 'You are presenting to the class.'
            : controlRequested
              ? 'Your request is waiting with the teacher.'
              : 'Ask the teacher when you want to present.'}</p>
        </div>
        {!isController ? <button
          className={controlRequested ? 'is-active' : ''}
          type="button"
          onClick={() => void toggleControlRequest()}
        >{controlRequested ? 'Cancel request' : 'Ask for control'}</button> : null}
      </section>
      <section>
        <h2>Ask at an exact point</h2>
        {pinMode ? <p className="classroom-pin-help">Move the crosshair to the exact tissue point, then tap its centre.</p> : null}
        <div className="classroom-row">
          <button className={pinMode ? 'is-active' : ''} type="button" onClick={() => setPinMode(true)}>{pin ? 'Choose another point' : 'Pin a point on the slide'}</button>
          {pin ? <button type="button" onClick={() => void removePin()}>Clear pin</button> : null}
        </div>
        <textarea value={question} maxLength={500} placeholder="What do you notice or want to ask?" onChange={(event) => setQuestion(event.target.value)} />
        <button className="primary" type="button" disabled={!pin || !question.trim()} onClick={() => void ask()}>Send question</button>
      </section>
      <section>
        <h2>My private notebook</h2>
        {!storage.indexedDb && <p role="alert">Local notebook storage is unavailable.</p>}
        <button
          className={drawing ? 'is-active' : ''}
          type="button"
          aria-pressed={drawing}
          onClick={() => {
            setPinMode(false)
            setDrawing((current) => !current)
          }}
        >{drawing ? 'Finish drawing' : 'Draw on slide'}</button>
        <textarea value={note} placeholder="Write a private note…" onChange={(event) => setNote(event.target.value)} />
        <button type="button" disabled={!storage.indexedDb} onClick={() => void capture()}>Save capture + note</button>
        <p className="classroom-storage-note">{entries.length}/100 entries · stored only in this browser</p>
        <div className="classroom-row">
          <button type="button" disabled={!entries.length} onClick={() => void shareLocal()}>Share / export</button>
          <button type="button" disabled={!entries.length} onClick={() => void printLocal()}>Print / PDF</button>
          <button type="button" disabled={!entries.length} onClick={() => {
            if (window.confirm('Delete this classroom notebook from this device?')) {
              void deleteSessionEntries(sessionId).then(() => setEntries([]))
            }
          }}>Delete local notes</button>
        </div>
        <p className="classroom-storage-note">Responsive offline notebook · share to Files or AirDrop on iPhone and iPad.</p>
      </section>
      {message && <p className="classroom-message" role="status">{message}</p>}
    </aside>
  </div>
}
