import { ChevronLeft, ChevronRight, Expand, Home, Menu, Minus, Plus, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getSharedManifest } from '../api'
import { OpenSeadragonViewer, type ViewerHandle } from '../components/OpenSeadragonViewer'
import type { SharedManifest } from '../types'
import '../shared-viewer.css'
import '../shared-message.css'

export function SharedViewerPage({ targetType }: { targetType: 'folder' | 'collection' }) {
  const { publicId = '' } = useParams()
  const [manifest, setManifest] = useState<SharedManifest | null>(null)
  const [position, setPosition] = useState(0)
  const [missing, setMissing] = useState(false)
  const [retry, setRetry] = useState(0)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [scaleBar, setScaleBar] = useState<{ microns: number; width: number } | null>(null)
  const controls = useRef<ViewerHandle | null>(null)
  const ready = useCallback((handle: ViewerHandle) => { controls.current = handle }, [])
  const storageKey = `pathlab-share-position:${targetType}:${publicId}`

  useEffect(() => {
    let active = true
    setMissing(false)
    setManifest(null)
    void getSharedManifest(targetType, publicId)
      .then((result) => {
        if (!active) return
        setManifest(result)
        const saved = Number(sessionStorage.getItem(storageKey))
        setPosition(Number.isInteger(saved) && saved >= 0 && saved < result.slides.length ? saved : 0)
      })
      .catch(() => { if (active) setMissing(true) })
    return () => { active = false }
  }, [publicId, retry, storageKey, targetType])

  const select = useCallback((next: number) => {
    if (!manifest?.slides.length) return
    const bounded = Math.max(0, Math.min(next, manifest.slides.length - 1))
    setPosition(bounded)
    sessionStorage.setItem(storageKey, String(bounded))
    setDrawerOpen(false)
  }, [manifest, storageKey])

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return
      if (event.key === 'ArrowRight') select(position + 1)
      if (event.key === 'ArrowLeft') select(position - 1)
      if (event.key === '+' || event.key === '=') controls.current?.zoomIn()
      if (event.key === '-') controls.current?.zoomOut()
      if (event.key === 'Escape') setDrawerOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [position, select])

  useEffect(() => {
    let robots = document.querySelector<HTMLMetaElement>('meta[name="robots"]')
    const previous = robots?.content
    const created = !robots
    if (!robots) {
      robots = document.createElement('meta')
      robots.name = 'robots'
      document.head.append(robots)
    }
    robots.content = 'noindex, nofollow, noarchive'
    return () => {
      if (created) robots?.remove()
      else if (robots && previous !== undefined) robots.content = previous
    }
  }, [])

  if (missing) {
    return (
      <main className="share-message">
        <h1>This shared library is unavailable</h1>
        <p>The link may be incorrect, expired, or revoked.</p>
        <button type="button" onClick={() => setRetry((current) => current + 1)}>
          Try again
        </button>
      </main>
    )
  }
  if (!manifest) return <div className="center-state dark">Opening shared library…</div>
  if (!manifest.slides.length) {
    return <main className="share-message"><h1>No slides are available</h1><p>This shared library is currently empty.</p></main>
  }
  const slide = manifest.slides[position]
  const filtered = manifest.slides.filter((item) => (
    `${item.displayName} ${item.organSite} ${item.stain} ${item.diagnosis}`
      .toLocaleLowerCase()
      .includes(search.toLocaleLowerCase())
  ))
  return (
    <div className={`shared-viewer-shell ${drawerOpen ? 'drawer-open' : ''}`}>
      <header className="shared-viewer-header">
        <button type="button" className="share-menu" aria-label="Open slide navigator" onClick={() => setDrawerOpen(true)}><Menu /></button>
        <div><p>PathLab Viewer</p><h1>{manifest.name}</h1></div>
        <span>{position + 1} / {manifest.slides.length}</span>
      </header>
      <button type="button" className="share-drawer-backdrop" aria-label="Close slide navigator" onClick={() => setDrawerOpen(false)} />
      <aside className="share-slide-rail" aria-label="Shared slides">
        <div className="share-rail-heading">
          <div><p>Teaching set</p><h2>{manifest.name}</h2></div>
          <button type="button" aria-label="Close slide navigator" onClick={() => setDrawerOpen(false)}><X /></button>
        </div>
        <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search this set" aria-label="Search shared slides" />
        <div className="share-slide-list">
          {filtered.map((item) => (
            <button key={item.position} type="button" className={item.position === position ? 'active' : ''} onClick={() => select(item.position)}>
              <img src={item.thumbnailUrl} alt="" loading="lazy" />
              <span><strong>{item.displayName}</strong><small>{[item.organSite, item.stain].filter(Boolean).join(' · ')}</small></span>
            </button>
          ))}
        </div>
      </aside>
      <main className="shared-viewer-stage">
        <OpenSeadragonViewer
          tileSource={slide.tileSource}
          onReady={ready}
          micronsPerPixel={slide.scale}
          onScaleChange={(microns, width) => setScaleBar({ microns, width })}
        />
        {slide.scale && scaleBar ? (
          <div className="shared-scale-bar" aria-label={`${scaleBar.microns} micrometers`}>
            <span>{scaleBar.microns} µm</span>
            <i style={{ width: `${scaleBar.width}px` }} />
          </div>
        ) : null}
        <div className="shared-slide-caption">
          <h2>{slide.displayName}</h2>
          <p>{[slide.organSite, slide.stain, slide.diagnosis].filter(Boolean).join(' · ')}</p>
        </div>
        <nav className="shared-viewer-tools" aria-label="Shared viewer controls">
          <button type="button" aria-label="Previous slide" disabled={position === 0} onClick={() => select(position - 1)}><ChevronLeft /></button>
          <button type="button" aria-label="Next slide" disabled={position === manifest.slides.length - 1} onClick={() => select(position + 1)}><ChevronRight /></button>
          <i />
          <button type="button" aria-label="Zoom in" onClick={() => controls.current?.zoomIn()}><Plus /></button>
          <button type="button" aria-label="Zoom out" onClick={() => controls.current?.zoomOut()}><Minus /></button>
          <button type="button" aria-label="Home view" onClick={() => controls.current?.home()}><Home /></button>
          <button type="button" aria-label="Fullscreen" onClick={() => controls.current?.fullscreen()}><Expand /></button>
        </nav>
      </main>
    </div>
  )
}
