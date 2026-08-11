import type OpenSeadragon from 'openseadragon'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, listSlides } from '../api'
import {
  answerQuestion,
  createClassroom,
  endClassroom,
  grantControl,
  openQuestion,
  publishTeacherViewport,
  revokeControl,
  teacherState,
  type CreatedClassroom,
  type TeacherState,
} from '../classroom/api'
import { Brand } from '../components/Brand'
import {
  OpenSeadragonViewer,
  type ViewerAttachmentCallback,
} from '../components/OpenSeadragonViewer'
import type { AdminSlide } from '../types'
import '../classroom/classroom.css'

const ACTIVE_CLASSROOM_KEY = 'pathlab-active-classroom:v1'

function savedClassroom(): CreatedClassroom | null {
  try {
    const value = sessionStorage.getItem(ACTIVE_CLASSROOM_KEY)
    return value ? JSON.parse(value) as CreatedClassroom : null
  } catch {
    return null
  }
}

function viewportPayload(viewer: OpenSeadragon.Viewer, slideId: string) {
  const center = viewer.viewport.getCenter(true)
  const image = viewer.viewport.viewportToImageCoordinates(center)
  const dimensions = viewer.world.getItemAt(0)?.source.dimensions
  return {
    slideId,
    x: dimensions ? image.x / dimensions.x : 0.5,
    y: dimensions ? image.y / dimensions.y : 0.5,
    zoom: viewer.viewport.getZoom(true),
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
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)
  const publishTimer = useRef<number | null>(null)

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
    setState(next)
    if (next.presenter.slideId) setSlideId(next.presenter.slideId)
  }, [])

  useEffect(() => {
    if (!classroom) return
    void refresh(classroom.id).catch(() => {
      sessionStorage.removeItem(ACTIVE_CLASSROOM_KEY)
      setClassroom(null)
      setError('The previous classroom is no longer active.')
    })
    const events = new EventSource(`/api/v1/admin/classroom/sessions/${classroom.id}/events`)
    const update = () => { void refresh(classroom.id).catch(() => undefined) }
    for (const name of [
      'stream-ready', 'participant-joined', 'participant-left',
      'participant-reconnected', 'question-added', 'question-removed', 'control',
    ]) events.addEventListener(name, update)
    return () => events.close()
  }, [classroom, refresh])

  const currentSlide = useMemo(
    () => classroom?.slides.find((slide) => slide.id === slideId) ?? classroom?.slides[0],
    [classroom, slideId],
  )

  const attachViewer = useCallback<ViewerAttachmentCallback>((viewer) => {
    viewerRef.current = viewer
    const publish = () => {
      if (!classroom || !currentSlide) return
      if (publishTimer.current !== null) window.clearTimeout(publishTimer.current)
      publishTimer.current = window.setTimeout(() => {
        publishTimer.current = null
        void publishTeacherViewport(classroom.id, viewportPayload(viewer, currentSlide.id))
      }, 250)
    }
    viewer.addHandler('animation-finish', publish)
    return () => {
      viewer.removeHandler('animation-finish', publish)
      viewerRef.current = null
      if (publishTimer.current !== null) window.clearTimeout(publishTimer.current)
    }
  }, [classroom, currentSlide])

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

  if (!classroom) return <main className="classroom-setup">
    <header><Brand variant="library" /><Link to="/admin">Back to library</Link></header>
    <section>
      <p className="eyebrow">Active classroom</p>
      <h1>Choose teaching slides</h1>
      <p>Only the selected published DZI versions are pinned for this session.</p>
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
      <button className="primary" type="button" disabled={!selected.length} onClick={() => void start()}>
        Start classroom
      </button>
    </section>
  </main>

  return <div className="classroom-shell classroom-shell--teacher">
    <header className="classroom-topbar">
      <Brand variant="library" />
      <div><span>Join code</span><strong>{classroom.joinCode}</strong></div>
      <button type="button" onClick={() => void endClassroom(classroom.id).then(() => {
        sessionStorage.removeItem(ACTIVE_CLASSROOM_KEY)
        setClassroom(null)
      })}>
        End class
      </button>
    </header>
    <main className="classroom-viewer">
      {currentSlide && <OpenSeadragonViewer
        tileSource={currentSlide.tileSource}
        onReady={() => undefined}
        onViewerAttach={attachViewer}
      />}
      <select value={currentSlide?.id ?? ''} onChange={(event) => setSlideId(event.target.value)}>
        {classroom.slides.map((slide) => <option key={slide.id} value={slide.id}>
          {slide.position + 1}. {slide.displayName}
        </option>)}
      </select>
    </main>
    <aside className="classroom-panel">
      {error && <p role="alert" className="classroom-error">{error}</p>}
      <section>
        <h2>Students <span>{state?.participants.length ?? 0}/300</span></h2>
        <ul>{state?.participants.map((participant) => {
          const isController = state.controller.participantId === participant.id
          return <li key={participant.id}>
            <div>
              <strong>{participant.alias}</strong>
              <small>{isController ? `${participant.status} · controller` : participant.status}</small>
            </div>
            <button type="button" onClick={() => void (isController
              ? revokeControl(classroom.id)
              : grantControl(classroom.id, participant.id)
            ).then(() => refresh(classroom.id)).catch(() => {
              setError('Slide control could not be changed.')
            })}>
              {isController ? 'Take back control' : 'Give control'}
            </button>
          </li>
        })}</ul>
      </section>
      <section>
        <h2>Questions <span>{state?.pendingQuestions.length ?? 0}/200</span></h2>
        <ul>{state?.pendingQuestions.map((question) => <li key={question.id}>
          <p>{question.text}</p>
          <div>
            <button type="button" onClick={() => void openQuestion(classroom.id, question.id)}>
              Show field
            </button>
            <button type="button" onClick={() => void answerQuestion(classroom.id, question.id)}>
              Answered
            </button>
          </div>
        </li>)}</ul>
      </section>
    </aside>
  </div>
}
