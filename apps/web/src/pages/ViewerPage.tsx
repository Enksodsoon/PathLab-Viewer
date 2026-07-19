import { useCallback, useEffect, useRef, useState } from 'react'
import { Expand, Home, Info, Minus, Plus } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { getPrivateSlide, getPublicSlide } from '../api'
import { Brand } from '../components/Brand'
import { OpenSeadragonViewer, type ViewerHandle } from '../components/OpenSeadragonViewer'
import type { AdminSlide, PublicSlide } from '../types'

export function ViewerPage() {
  const { publicId, slideId } = useParams()
  const [slide, setSlide] = useState<PublicSlide | AdminSlide | null>(null)
  const [missing, setMissing] = useState(false)
  const [scaleInfo, setScaleInfo] = useState({ microns: 100, width: 86 })
  const controls = useRef<ViewerHandle | null>(null)
  const ready = useCallback((handle: ViewerHandle) => { controls.current = handle }, [])
  const updateScale = useCallback((microns: number, width: number) => {
    setScaleInfo({ microns, width })
  }, [])
  useEffect(() => {
    let active = true
    const request = slideId ? getPrivateSlide(slideId) : getPublicSlide(publicId ?? '')
    void request.then((result) => { if (active) setSlide(result) }).catch(() => { if (active) setMissing(true) })
    return () => { active = false }
  }, [publicId, slideId])
  useEffect(() => {
    let robots = document.querySelector<HTMLMetaElement>('meta[name="robots"]')
    if (!robots) { robots = document.createElement('meta'); robots.name = 'robots'; document.head.append(robots) }
    robots.content = 'noindex, nofollow, noarchive'
  }, [])
  if (missing) return <main className="viewer-message"><Brand /><div><h1>This slide is unavailable</h1><p>The link may be incorrect, unpublished, or removed.</p></div></main>
  if (!slide) return <div className="center-state dark">Opening slide…</div>
  const scale = slide.metadata?.physicalSizeX
  return <div className="viewer-shell">
    <header className="viewer-header"><Brand /><div className="viewer-title"><strong>{slide.displayName}</strong><span>{slide.metadata ? `${slide.metadata.width.toLocaleString()} × ${slide.metadata.height.toLocaleString()} px` : 'Whole-slide image'}</span></div><span className="viewer-help"><Info size={15} /> Scroll or pinch to zoom</span></header>
    <main className="viewer-stage">
      <OpenSeadragonViewer tileSource={slide.tileSource ?? ''} onReady={ready} micronsPerPixel={scale} onScaleChange={updateScale} />
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
