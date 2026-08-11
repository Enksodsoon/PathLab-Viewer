import OpenSeadragon from 'openseadragon'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import {
  joinClassroom,
  publishStudentViewport,
  studentState,
  submitQuestion,
  type StudentState,
} from '../classroom/api'
import {
  deleteSessionEntries,
  exportNotebook,
  listEntries,
  saveEntry,
  storageCapability,
  type NotebookEntry,
  type StorageCapability,
} from '../classroom/notebook'
import { captureVisibleTissue } from '../classroom/screenshot'
import { Brand } from '../components/Brand'
import {
  OpenSeadragonViewer,
  type ViewerAttachmentCallback,
} from '../components/OpenSeadragonViewer'
import '../classroom/classroom.css'

interface Pin {
  x: number
  y: number
  zoom: number
  left: number
  top: number
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
  const [pin, setPin] = useState<Pin | null>(null)
  const [question, setQuestion] = useState('')
  const [note, setNote] = useState('')
  const [entries, setEntries] = useState<NotebookEntry[]>([])
  const [storage, setStorage] = useState<StorageCapability>({ indexedDb: false })
  const [message, setMessage] = useState('')
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)
  const suppressPublish = useRef(false)
  const followRef = useRef(follow)
  const stateRef = useRef<StudentState | null>(null)
  const slideIdRef = useRef(slideId)
  const csrfRef = useRef(csrfToken)
  const publishTimer = useRef<number | null>(null)
  const streamEpoch = useRef('')
  const streamSequence = useRef(0)

  useEffect(() => { stateRef.current = state }, [state])
  useEffect(() => { followRef.current = follow }, [follow])
  useEffect(() => { slideIdRef.current = slideId }, [slideId])
  useEffect(() => { csrfRef.current = csrfToken }, [csrfToken])
  useEffect(() => { void storageCapability().then(setStorage) }, [])
  useEffect(() => {
    if (!sessionId || csrfToken) return
    void studentState(sessionId).then(async (next) => {
      setState(next)
      setCsrfToken(next.csrfToken)
      setAlias(next.participant.alias)
      if (next.presenter.slideId) setSlideId(next.presenter.slideId)
      setEntries(await listEntries(sessionId))
    }).catch(() => setMessage('Rejoin with the classroom code to continue.'))
  }, [csrfToken, sessionId])

  const refresh = useCallback(async (id: string) => {
    const next = await studentState(id)
    setState(next)
    if (follow && next.presenter.slideId) setSlideId(next.presenter.slideId)
    setEntries(await listEntries(id))
  }, [follow])

  useEffect(() => {
    if (!sessionId || !csrfToken) return
    void refresh(sessionId)
    const events = new EventSource(`/api/v1/classroom/sessions/${sessionId}/events`)
    const recover = () => { void refresh(sessionId).catch(() => undefined) }
    const sequence = (event: Event): Record<string, unknown> | null => {
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
        if (epoch !== streamEpoch.current || next !== streamSequence.current + 1) {
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
    events.addEventListener('stream-ready', (event) => { sequence(event); recover() })
    events.addEventListener('presenter', (event) => {
      const payload = sequence(event)
      if (!payload || typeof payload.presenterSequence !== 'number'
        || typeof payload.slideId !== 'string' || !payload.viewport) return
      setState((current) => current ? {
        ...current,
        presenter: {
          sequence: payload.presenterSequence as number,
          slideId: payload.slideId as string,
          viewport: payload.viewport as { x: number; y: number; zoom: number },
        },
      } : current)
      if (followRef.current) setSlideId(payload.slideId as string)
    })
    for (const name of ['control', 'session-ended']) {
      events.addEventListener(name, (event) => { if (sequence(event)) recover() })
    }
    events.addEventListener('question-removed', (event) => {
      const payload = sequence(event)
      if (!payload || typeof payload.questionId !== 'string') return
      setState((current) => current ? {
        ...current,
        pendingQuestionIds: current.pendingQuestionIds.filter(
          (questionId) => questionId !== payload.questionId,
        ),
      } : current)
    })
    return () => events.close()
  }, [csrfToken, refresh, sessionId])

  const currentSlide = useMemo(
    () => state?.slides.find((slide) => slide.id === slideId) ?? state?.slides[0],
    [slideId, state],
  )

  const applyRemote = useCallback((viewer: OpenSeadragon.Viewer) => {
    const current = stateRef.current
    const presenter = current?.presenter
    const slide = current?.slides.find((item) => item.id === slideIdRef.current)
    if (!follow || !presenter?.viewport || presenter.slideId !== slide?.id || !slide) return
    suppressPublish.current = true
    const point = viewer.viewport.imageToViewportCoordinates(
      presenter.viewport.x * slide.width,
      presenter.viewport.y * slide.height,
    )
    viewer.viewport.panTo(point, true)
    viewer.viewport.zoomTo(presenter.viewport.zoom, point, true)
    viewer.viewport.applyConstraints()
    window.setTimeout(() => { suppressPublish.current = false }, 0)
  }, [follow])

  useEffect(() => {
    if (viewerRef.current) applyRemote(viewerRef.current)
  }, [applyRemote, state])

  const attachViewer = useCallback<ViewerAttachmentCallback>((viewer) => {
    viewerRef.current = viewer
    const opened = () => applyRemote(viewer)
    const moved = () => {
      const current = stateRef.current
      if (suppressPublish.current || !current?.control.isController
        || !current.control.leaseId || !sessionId) return
      if (publishTimer.current !== null) window.clearTimeout(publishTimer.current)
      publishTimer.current = window.setTimeout(() => {
        publishTimer.current = null
        void publishStudentViewport(
          sessionId,
          csrfRef.current,
          current.control.leaseId!,
          normalizedViewport(viewer, slideIdRef.current),
        ).catch(() => setMessage('Slide control returned to the teacher.'))
      }, 250)
    }
    const clicked = (event: { position: OpenSeadragon.Point }) => {
      if (!pinMode || !currentSlide) return
      const image = viewer.viewport.viewportToImageCoordinates(
        viewer.viewport.pointFromPixel(event.position, true),
      )
      setPin({
        x: Math.max(0, Math.min(1, image.x / currentSlide.width)),
        y: Math.max(0, Math.min(1, image.y / currentSlide.height)),
        zoom: viewer.viewport.getZoom(true),
        left: event.position.x / viewer.container.clientWidth * 100,
        top: event.position.y / viewer.container.clientHeight * 100,
      })
      setPinMode(false)
    }
    viewer.addHandler('open', opened)
    viewer.addHandler('animation-finish', moved)
    viewer.addHandler('canvas-click', clicked)
    return () => {
      viewer.removeHandler('open', opened)
      viewer.removeHandler('animation-finish', moved)
      viewer.removeHandler('canvas-click', clicked)
      viewerRef.current = null
    }
  }, [applyRemote, currentSlide, pinMode, sessionId])

  const join = async () => {
    setMessage('')
    try {
      const joined = await joinClassroom(joinCode.trim().toUpperCase(), displayName)
      setCsrfToken(joined.csrfToken)
      setAlias(joined.participant.alias)
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

  const capture = async () => {
    if (!sessionId || !currentSlide || !viewerRef.current) return
    let image: Blob | undefined
    try {
      const canvas = largestCanvas(viewerRef.current)
      if (!canvas) throw new Error('The tissue view is not ready')
      image = (await captureVisibleTissue(canvas)).blob
    } catch (error) {
      if (!note.trim()) {
        setMessage(error instanceof Error ? error.message : 'Screenshot failed.')
        return
      }
      setMessage('Screenshot failed, but the text note was preserved.')
    }
    const entry: NotebookEntry = {
      id: crypto.randomUUID(),
      sessionId,
      slideId: currentSlide.id,
      slideName: currentSlide.displayName,
      note: note.trim(),
      createdAt: new Date().toISOString(),
      image,
    }
    await saveEntry(entry)
    setEntries((current) => [...current, entry])
    setNote('')
    if (image) setMessage('Screenshot and note saved on this device only.')
  }

  const exportLocal = async () => {
    const blob = await exportNotebook('PathLab classroom notebook', entries)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'pathlab-classroom-notebook.html'
    anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  if (!sessionId || !csrfToken) return <main className="classroom-join">
    <Brand variant="library" />
    <section>
      <p className="eyebrow">PathLab classroom</p>
      <h1>Join a slide session</h1>
      <label>Join code<input value={joinCode} maxLength={16} onChange={(event) => setJoinCode(event.target.value)} /></label>
      <label>Name (optional)<input value={displayName} maxLength={80} onChange={(event) => setDisplayName(event.target.value)} /></label>
      <button className="primary" type="button" disabled={joinCode.length < 6} onClick={() => void join()}>Join</button>
      {message && <p role="status">{message}</p>}
    </section>
  </main>

  return <div className="classroom-shell classroom-shell--student">
    <header className="classroom-topbar">
      <Brand variant="library" />
      <strong>{alias || 'Private learner'}</strong>
      <label><input type="checkbox" checked={follow} onChange={(event) => setFollow(event.target.checked)} /> Follow teacher</label>
    </header>
    <main className={`classroom-viewer${pinMode ? ' is-pin-mode' : ''}`}>
      {currentSlide && <OpenSeadragonViewer
        tileSource={currentSlide.tileSource}
        onReady={() => undefined}
        onViewerAttach={attachViewer}
      />}
      {pin && <span className="classroom-pin" style={{ left: `${pin.left}%`, top: `${pin.top}%` }} />}
      <select value={currentSlide?.id ?? ''} onChange={(event) => { setFollow(false); setSlideId(event.target.value) }}>
        {state?.slides.map((slide) => <option key={slide.id} value={slide.id}>{slide.displayName}</option>)}
      </select>
    </main>
    <aside className="classroom-panel">
      <section>
        <h2>Ask at an exact point</h2>
        <button type="button" onClick={() => setPinMode(true)}>{pin ? 'Choose another point' : 'Pin a point on the slide'}</button>
        <textarea value={question} maxLength={500} placeholder="What do you notice or want to ask?" onChange={(event) => setQuestion(event.target.value)} />
        <button className="primary" type="button" disabled={!pin || !question.trim()} onClick={() => void ask()}>Send question</button>
      </section>
      <section>
        <h2>My private notebook</h2>
        {!storage.indexedDb && <p role="alert">Local notebook storage is unavailable.</p>}
        <textarea value={note} placeholder="Write a private note…" onChange={(event) => setNote(event.target.value)} />
        <button type="button" disabled={!storage.indexedDb} onClick={() => void capture()}>Capture tissue + save note</button>
        <p>{entries.length}/100 entries · stored only in this browser</p>
        <div className="classroom-row">
          <button type="button" disabled={!entries.length} onClick={() => void exportLocal()}>Export HTML</button>
          <button type="button" disabled={!entries.length} onClick={() => {
            if (window.confirm('Delete this classroom notebook from this device?')) {
              void deleteSessionEntries(sessionId).then(() => setEntries([]))
            }
          }}>Delete local notes</button>
        </div>
      </section>
      {message && <p role="status">{message}</p>}
    </aside>
  </div>
}
