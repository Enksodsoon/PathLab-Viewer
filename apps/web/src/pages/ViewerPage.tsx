import { ArrowsOut as Expand, House as Home, Info, Minus, Plus } from '@phosphor-icons/react'
import {
  type ComponentType,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, getPrivateSlide, getPublicSlide } from '../api'
import { Brand } from '../components/Brand'
import { Loader } from '../components/Loader'
import {
  OpenSeadragonViewer,
  type ViewerAttachmentCallback,
  type ViewerHandle,
} from '../components/OpenSeadragonViewer'
import { ThemeControl } from '../theme/ThemeControl'
import type { AdminSlide, PublicSlide } from '../types'

export function ViewerPage() {
  const { publicId, slideId } = useParams()
  const [slide, setSlide] = useState<PublicSlide | AdminSlide | null>(null)
  const [missing, setMissing] = useState(false)
  const [authExpired, setAuthExpired] = useState(false)
  const [annotationWorkspace, setAnnotationWorkspace] = useState<ComponentType<{
    slideId: string
    slideName: string
    onAttachmentChange: (attachment?: ViewerAttachmentCallback) => void
  }> | null>(null)
  const [annotationAttachment, setAnnotationAttachment] = useState<
    ViewerAttachmentCallback | undefined
  >()
  const [annotationLoadError, setAnnotationLoadError] = useState(false)
  const [annotationLoadAttempt, setAnnotationLoadAttempt] = useState(0)
  const [scaleInfo, setScaleInfo] = useState({ microns: 100, width: 86 })
  const controls = useRef<ViewerHandle | null>(null)
  const ready = useCallback((handle: ViewerHandle) => { controls.current = handle }, [])
  const updateScale = useCallback((microns: number, width: number) => {
    setScaleInfo({ microns, width })
  }, [])
  const updateAnnotationAttachment = useCallback((
    attachment?: ViewerAttachmentCallback,
  ) => {
    setAnnotationAttachment(() => attachment)
  }, [])
  useEffect(() => {
    let active = true
    setMissing(false)
    setAuthExpired(false)
    setSlide(null)
    const request = slideId ? getPrivateSlide(slideId) : getPublicSlide(publicId ?? '')
    void request.then((result) => {
      if (active) setSlide(result)
    }).catch((caught) => {
      if (!active) return
      if (slideId && caught instanceof ApiError && caught.status === 401) {
        setAuthExpired(true)
      } else {
        setMissing(true)
      }
    })
    return () => { active = false }
  }, [publicId, slideId])
  useEffect(() => {
    let active = true
    const enabled = Boolean(
      slideId
      && slide
      && 'id' in slide
      && slide.annotationsEnabled,
    )
    if (!enabled) {
      setAnnotationWorkspace(null)
      setAnnotationAttachment(undefined)
      setAnnotationLoadError(false)
      return () => { active = false }
    }
    setAnnotationLoadError(false)
    void import('../annotations/AnnotationWorkspace')
      .then((module) => {
        if (active) setAnnotationWorkspace(() => module.AnnotationWorkspace)
      })
      .catch(() => {
        if (active) {
          setAnnotationWorkspace(null)
          setAnnotationAttachment(undefined)
          setAnnotationLoadError(true)
        }
      })
    return () => {
      active = false
      setAnnotationAttachment(undefined)
    }
  }, [annotationLoadAttempt, slide, slideId])
  useEffect(() => {
    let robots = document.querySelector<HTMLMetaElement>('meta[name="robots"]')
    if (!robots) { robots = document.createElement('meta'); robots.name = 'robots'; document.head.append(robots) }
    robots.content = 'noindex, nofollow, noarchive'
  }, [])
  if (authExpired) return <main className="viewer-message"><Brand /><div><h1>Administrator session expired</h1><p>Sign in again to reopen this private slide and its annotation tools.</p><Link className="button primary" to="/admin">Sign in again</Link></div></main>
  if (missing) return <main className="viewer-message"><Brand /><div><h1>This slide is unavailable</h1><p>The link may be incorrect, private, or removed.</p></div></main>
  if (!slide) return <Loader label="Opening slide…" size="large" fullscreen />
  const scale = slide.metadata?.physicalSizeX
  const annotationsEnabled = Boolean(
    slideId
    && 'id' in slide
    && slide.annotationsEnabled,
  )
  const AnnotationWorkspace = annotationWorkspace
  return <div className="viewer-shell">
    <header className="viewer-header">
      <Brand variant="library" />
      <div className="viewer-title">
        <strong>{slide.displayName}</strong>
        <span>{slide.metadata ? `${slide.metadata.width.toLocaleString()} × ${slide.metadata.height.toLocaleString()} px` : 'Whole-slide image'}</span>
      </div>
      <span className="viewer-help"><Info size={15} /> Scroll or pinch to zoom</span>
      <ThemeControl compact className="viewer-theme-control" />
    </header>
    <main className={`viewer-stage${annotationsEnabled ? ' viewer-stage--annotations' : ''}`}>
      <OpenSeadragonViewer
        tileSource={slide.tileSource ?? ''}
        posterUrl={slide.thumbnailUrl}
        onReady={ready}
        micronsPerPixel={scale}
        onScaleChange={updateScale}
        onViewerAttach={annotationsEnabled ? annotationAttachment : undefined}
      />
      {annotationsEnabled && AnnotationWorkspace && slideId ? (
        <AnnotationWorkspace
          slideId={slideId}
          slideName={slide.displayName}
          onAttachmentChange={updateAnnotationAttachment}
        />
      ) : null}
      {annotationsEnabled && !AnnotationWorkspace && !annotationLoadError ? (
        <div className="annotation-private-loading">
          <Loader label="Opening annotation tools…" size="small" inline />
        </div>
      ) : null}
      {annotationsEnabled && annotationLoadError ? (
        <div className="annotation-private-failure" role="alert">
          <span>Annotation tools could not load. Slide navigation is still available.</span>
          <button
            type="button"
            onClick={() => setAnnotationLoadAttempt((attempt) => attempt + 1)}
          >
            Retry annotations
          </button>
        </div>
      ) : null}
      <nav className="viewer-tools" aria-label="Viewer controls">
        <button aria-label="Zoom in" title="Zoom in" onClick={() => controls.current?.zoomIn()}><Plus /></button>
        <button aria-label="Zoom out" title="Zoom out" onClick={() => controls.current?.zoomOut()}><Minus /></button>
        <span />
        <button aria-label="Home view" title="Home view" onClick={() => controls.current?.home()}><Home /></button>
        <button aria-label="Fullscreen" title="Fullscreen" onClick={() => controls.current?.fullscreen()}><Expand /></button>
      </nav>
      {scale && <div className="scale-bar"><i style={{ width: `${scaleInfo.width}px` }} /><span>{scaleInfo.microns.toLocaleString()} µm</span></div>}
    </main>
  </div>
}
