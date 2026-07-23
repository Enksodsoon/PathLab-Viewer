import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Expand, Home, Minus, Plus } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { getPublicFolder } from '../api'
import { Brand } from '../components/Brand'
import { OpenSeadragonViewer, type ViewerHandle } from '../components/OpenSeadragonViewer'
import type { PublicFolderManifest } from '../types'

export function FolderViewerPage() {
  const { folderPublicId = '' } = useParams()
  const [manifest, setManifest] = useState<PublicFolderManifest | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [missing, setMissing] = useState(false)
  const controls = useRef<ViewerHandle | null>(null)
  const ready = useCallback((handle: ViewerHandle) => { controls.current = handle }, [])
  useEffect(() => {
    let active = true
    void getPublicFolder(folderPublicId).then((result) => {
      if (!active) return
      const key = `pathlab-folder:${folderPublicId}:slide`
      const stored = localStorage.getItem(key)
      const initial = result.slides.some((slide) => slide.publicId === stored)
        ? stored ?? ''
        : result.slides[0]?.publicId ?? ''
      setManifest(result)
      setSelectedId(initial)
    }).catch(() => { if (active) setMissing(true) })
    return () => { active = false }
  }, [folderPublicId])
  function select(publicId: string) {
    setSelectedId(publicId)
    localStorage.setItem(`pathlab-folder:${folderPublicId}:slide`, publicId)
  }
  if (missing) return <main className="viewer-message"><Brand /><div><h1>This folder is unavailable</h1><p>The link may be incorrect, expired, revoked, or removed.</p></div></main>
  if (!manifest) return <div className="center-state dark">Opening folder…</div>
  if (!manifest.slides.length) return <main className="viewer-message"><Brand /><div><h1>{manifest.name}</h1><p>No published slides are available.</p></div></main>
  const index = Math.max(0, manifest.slides.findIndex((slide) => slide.publicId === selectedId))
  const slide = manifest.slides[index]
  return <div className="folder-viewer-shell">
    <header className="folder-viewer-header"><Brand /><div><strong>{manifest.name}</strong><span>{index + 1} of {manifest.slides.length}</span></div></header>
    <aside className="folder-slide-sidebar"><h1>{manifest.name}</h1>{manifest.description ? <p>{manifest.description}</p> : null}
      {manifest.slides.map((item) => <button className={item.publicId === slide.publicId ? 'active' : ''} key={item.publicId} onClick={() => select(item.publicId)}>{item.displayName}</button>)}
    </aside>
    <main className="folder-viewer-main">
      <div className="folder-mobile-selector"><label>Slide<select value={slide.publicId} onChange={(event) => select(event.target.value)}>{manifest.slides.map((item) => <option key={item.publicId} value={item.publicId}>{item.displayName}</option>)}</select></label></div>
      <div className="folder-slide-heading"><div><h2>{slide.displayName}</h2><p>{[slide.stain, slide.organSite].filter(Boolean).join(' · ')}</p></div><nav aria-label="Slide navigation"><button aria-label="Previous slide" disabled={index === 0} onClick={() => select(manifest.slides[index - 1].publicId)}><ChevronLeft /></button><button aria-label="Next slide" disabled={index === manifest.slides.length - 1} onClick={() => select(manifest.slides[index + 1].publicId)}><ChevronRight /></button></nav></div>
      <div className="folder-osd-stage"><OpenSeadragonViewer tileSource={slide.tileSource} onReady={ready} micronsPerPixel={slide.metadata?.physicalSizeX} />
        <nav className="viewer-tools" aria-label="Viewer controls"><button aria-label="Zoom in" onClick={() => controls.current?.zoomIn()}><Plus /></button><button aria-label="Zoom out" onClick={() => controls.current?.zoomOut()}><Minus /></button><span /><button aria-label="Home view" onClick={() => controls.current?.home()}><Home /></button><button aria-label="Fullscreen" onClick={() => controls.current?.fullscreen()}><Expand /></button></nav>
      </div>
      <details className="folder-slide-details"><summary>Slide information</summary>{slide.description ? <p>{slide.description}</p> : null}{slide.teachingNote ? <p>{slide.teachingNote}</p> : null}{slide.tags.length ? <p>{slide.tags.join(', ')}</p> : null}</details>
    </main>
  </div>
}
