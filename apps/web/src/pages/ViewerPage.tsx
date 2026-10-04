import { ArrowLeft, CaretLeft, CaretRight, ArrowsOut as Expand, House as Home, Info, Minus, Plus } from '@phosphor-icons/react'
import {
  type ComponentType,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { ApiError, getPrivateSlide, getPublicSlide } from '../api'
import { normalizedMicronsPerPixel } from '../calibration'
import { adminSignInPath } from '../authReturnPath'
import { ignoresShortcut, readLibraryContext } from '../components/library/viewerNavigation'
import '../components/library/viewerJourney.css'
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
  const location = useLocation()
  const navigate = useNavigate()
  const library = slideId ? readLibraryContext(location.state) : null
  const currentIndex = library?.slides.findIndex((item) => item.id === slideId) ?? -1
  const previous = currentIndex > 0 ? library?.slides[currentIndex - 1] : undefined
  const next = currentIndex >= 0 ? library?.slides[currentIndex + 1] : undefined
  const goToSlide = useCallback((id: string) => navigate(`/admin/preview/${encodeURIComponent(id)}`, { state: location.state, replace: true }), [navigate, location.state])
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (ignoresShortcut(event.target) || event.altKey || event.ctrlKey || event.metaKey || document.querySelector('dialog[open], [role="dialog"], [role="menu"]')) return
      const destination = event.key === 'ArrowLeft' ? previous : event.key === 'ArrowRight' ? next : undefined
      if (destination) { event.preventDefault(); goToSlide(destination.id) }
    }
    window.addEventListener('keydown', keydown)
    return () => window.removeEventListener('keydown', keydown)
  }, [previous, next, goToSlide])
  const [slide, setSlide] = useState<PublicSlide | AdminSlide | null>(null)
  const [loadError, setLoadError] = useState<'unavailable' | 'retryable' | null>(null)
  const [authExpired, setAuthExpired] = useState(false)
  const [loadAttempt, setLoadAttempt] = useState(0)
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
    setLoadError(null)
    setAuthExpired(false)
    setSlide(null)
    controls.current = null
    const request = slideId ? getPrivateSlide(slideId) : getPublicSlide(publicId ?? '')
    void request.then((result) => {
      if (active) setSlide(result)
    }).catch((caught) => {
      if (!active) return
      if (slideId && caught instanceof ApiError && caught.status === 401) {
        setAuthExpired(true)
      } else if (caught instanceof ApiError && (caught.status === 404 || caught.status === 410)) {
        setLoadError('unavailable')
      } else setLoadError('retryable')
    })
    return () => { active = false }
  }, [loadAttempt, publicId, slideId])
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
  const returnLink = slideId
    ? <Link className="viewer-library-return" to={library?.returnTo ?? '/admin'}><ArrowLeft /> Library</Link>
    : <Link className="viewer-library-return" to="/"><Home /> Home</Link>
  const intendedPath = `${location.pathname}${location.search}${location.hash}`
  if (authExpired) return <main className="viewer-message"><Brand />{returnLink}<div><h1>Administrator session expired</h1><p>Sign in again to reopen this private slide and its annotation tools.</p><Link className="button primary" to={adminSignInPath(intendedPath)}>Sign in again</Link></div></main>
  if (loadError === 'unavailable') return <main className="viewer-message"><Brand />{returnLink}<div><h1>This slide is unavailable</h1><p>The link may be incorrect, private, or removed.</p></div></main>
  if (loadError === 'retryable') return <main className="viewer-message"><Brand />{returnLink}<div><h1>This slide could not be opened</h1><p>PathLab could not reach the slide service. Check your connection and try again.</p><button className="button primary" type="button" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>Retry</button></div></main>
  if (!slide) return <main className="viewer-message"><Brand />{returnLink}<Loader label="Opening slide…" size="large" inline /></main>
  const scale = normalizedMicronsPerPixel(slide.metadata)?.[0]
  const annotationsEnabled = Boolean(
    slideId
    && 'id' in slide
    && slide.annotationsEnabled,
  )
  const AnnotationWorkspace = annotationWorkspace
  return <div className="viewer-shell">
    <header className="viewer-header">
      {slideId ? <Link className="viewer-library-return" to={library?.returnTo ?? '/admin'}><ArrowLeft /> Library</Link> : <Brand variant="library" />}
      {library && currentIndex >= 0 ? <nav className="viewer-adjacent" aria-label="Slides in this library view">
        <button type="button" aria-label="Previous slide" disabled={!previous} onClick={() => previous && goToSlide(previous.id)}><CaretLeft /></button>
        <span>{currentIndex + 1} / {library.slides.length}</span>
        <button type="button" aria-label="Next slide" disabled={!next} onClick={() => next && goToSlide(next.id)}><CaretRight /></button>
      </nav> : null}
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
        micronsPerPixelY={normalizedMicronsPerPixel(slide.metadata)?.[1]}
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
      {!scale && <div className="scale-bar"><span>Relative scale: physical calibration unavailable</span></div>}
      {scale && <div className="scale-bar" title={scale !== normalizedMicronsPerPixel(slide.metadata)?.[1] ? 'Horizontal physical scale (anisotropic pixels)' : undefined}><i style={{ width: `${scaleInfo.width}px` }} /><span>{scaleInfo.microns.toLocaleString()} µm{scale !== normalizedMicronsPerPixel(slide.metadata)?.[1] ? ' (horizontal)' : ''}</span></div>}
    </main>
  </div>
}
