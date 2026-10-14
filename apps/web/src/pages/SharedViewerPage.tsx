import {
  ArrowsOut as Expand,
  CaretLeft as ChevronLeft,
  CaretRight as ChevronRight,
  FolderSimple,
  House as Home,
  List as Menu,
  Minus,
  Plus,
  X,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getSharedManifest } from '../api'
import { Loader } from '../components/Loader'
import { ignoresShortcut } from '../components/library/viewerNavigation'
import { OpenSeadragonViewer, type ViewerHandle } from '../components/OpenSeadragonViewer'
import { ThemeControl } from '../theme/ThemeControl'
import type { SharedManifest, SharedSlide } from '../types'
import '../shared-viewer.css'
import '../shared-message.css'

interface SharedFolderNode {
  key: string
  name: string
  slides: SharedSlide[]
  children: SharedFolderNode[]
}

function folderKey(path: string[]) {
  return JSON.stringify(path)
}

function buildFolderTree(
  rootName: string,
  folders: string[][],
  slides: SharedSlide[],
): SharedFolderNode {
  const root: SharedFolderNode = { key: 'root', name: rootName, slides: [], children: [] }
  const nodes = new Map<string, SharedFolderNode>([[folderKey([]), root]])

  function ensurePath(path: string[]) {
    let parent = root
    for (let depth = 1; depth <= path.length; depth += 1) {
      const currentPath = path.slice(0, depth)
      const key = folderKey(currentPath)
      let current = nodes.get(key)
      if (!current) {
        current = { key, name: currentPath.at(-1) ?? '', slides: [], children: [] }
        nodes.set(key, current)
        parent.children.push(current)
      }
      parent = current
    }
    return parent
  }

  folders.forEach((path) => ensurePath(path))
  slides.forEach((slide) => ensurePath(slide.folderPath ?? []).slides.push(slide))
  nodes.forEach((node) => node.children.sort((left, right) => left.name.localeCompare(right.name)))
  return root
}

function folderSlideCount(node: SharedFolderNode): number {
  return node.slides.length
    + node.children.reduce((total, child) => total + folderSlideCount(child), 0)
}

function SharedSlideButton({
  item,
  position,
  select,
}: {
  item: SharedSlide
  position: number
  select: (position: number) => void
}) {
  return (
    <button type="button" className={item.position === position ? 'active' : ''} aria-current={item.position === position ? 'page' : undefined} onClick={() => select(item.position)}>
      <img src={item.thumbnailUrl} alt="" loading="lazy" />
      <span><strong>{item.displayName}</strong><small>{[item.organSite, item.stain].filter(Boolean).join(' · ')}</small></span>
    </button>
  )
}

function SharedFolderBranch({
  node,
  position,
  select,
}: {
  node: SharedFolderNode
  position: number
  select: (position: number) => void
}) {
  return (
    <details className="share-folder-node" open>
      <summary>
        <FolderSimple />
        <span>{node.name}</span>
        <small>{folderSlideCount(node)}</small>
      </summary>
      <div className="share-folder-contents">
        {node.slides.map((item) => (
          <SharedSlideButton key={item.position} item={item} position={position} select={select} />
        ))}
        {node.children.map((child) => (
          <SharedFolderBranch key={child.key} node={child} position={position} select={select} />
        ))}
      </div>
    </details>
  )
}

export function SharedViewerPage({ targetType }: { targetType: 'folder' | 'collection' }) {
  const { publicId = '' } = useParams()
  const [manifest, setManifest] = useState<SharedManifest | null>(null)
  const [position, setPosition] = useState(0)
  const [missing, setMissing] = useState(false)
  const [retry, setRetry] = useState(0)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [narrowLayout, setNarrowLayout] = useState(() => (
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(max-width: 760px)').matches
      : false
  ))
  const [search, setSearch] = useState('')
  const [scaleBar, setScaleBar] = useState<{ microns: number; width: number } | null>(null)
  const controls = useRef<ViewerHandle | null>(null)
  const navigatorTrigger = useRef<HTMLButtonElement | null>(null)
  const navigatorClose = useRef<HTMLButtonElement | null>(null)
  const slideRail = useRef<HTMLElement | null>(null)
  const headerTitle = useRef<HTMLHeadingElement | null>(null)
  const drawerOpenRef = useRef(drawerOpen)
  const wasDrawerOpen = useRef(false)
  const ready = useCallback((handle: ViewerHandle) => { controls.current = handle }, [])

  const restoreNavigatorFocus = useCallback(() => {
    if (narrowLayout && navigatorTrigger.current?.getClientRects().length) {
      navigatorTrigger.current.focus()
      return
    }
    headerTitle.current?.focus()
  }, [narrowLayout])
  const closeNavigator = useCallback(() => {
    drawerOpenRef.current = false
    setDrawerOpen(false)
  }, [])
  const openNavigator = useCallback(() => {
    drawerOpenRef.current = true
    setDrawerOpen(true)
  }, [])

  useEffect(() => {
    const media = window.matchMedia('(max-width: 760px)')
    const updateLayout = (event: MediaQueryListEvent) => {
      setNarrowLayout(event.matches)
      if (!event.matches && drawerOpenRef.current) {
        drawerOpenRef.current = false
        setDrawerOpen(false)
        window.requestAnimationFrame(() => headerTitle.current?.focus())
      }
    }
    setNarrowLayout(media.matches)
    media.addEventListener('change', updateLayout)
    return () => media.removeEventListener('change', updateLayout)
  }, [])

  useLayoutEffect(() => {
    if (drawerOpen && narrowLayout) {
      navigatorClose.current?.focus()
    } else if (wasDrawerOpen.current) {
      restoreNavigatorFocus()
    }
    wasDrawerOpen.current = drawerOpen
  }, [drawerOpen, narrowLayout, restoreNavigatorFocus])

  useEffect(() => {
    if (!drawerOpen || !narrowLayout) return
    const handleDrawerKeys = (event: KeyboardEvent) => {
      if (event.defaultPrevented || (event.target instanceof Element && event.target.closest('dialog[open]'))) return
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        closeNavigator()
        return
      }
      if (event.key !== 'Tab') return
      const items = [...(slideRail.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), summary, a[href], [tabindex]:not([tabindex="-1"])',
      ) ?? [])].filter((item) => item.getClientRects().length > 0)
      if (!items.length) {
        event.preventDefault()
        slideRail.current?.focus()
        return
      }
      const first = items[0]
      const last = items.at(-1)!
      if (event.shiftKey && (document.activeElement === first || !slideRail.current?.contains(document.activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !slideRail.current?.contains(document.activeElement))) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleDrawerKeys, true)
    return () => document.removeEventListener('keydown', handleDrawerKeys, true)
  }, [closeNavigator, drawerOpen, narrowLayout])
  const storageKey = `pathlab-share-position:${targetType}:${publicId}`

  useEffect(() => {
    let active = true
    setMissing(false)
    setManifest(null)
    void getSharedManifest(targetType, publicId)
      .then((result) => {
        if (!active) return
        setManifest(result)
        let saved = 0
        try { saved = Number(sessionStorage.getItem(storageKey)) } catch { /* Position memory is optional. */ }
        setPosition(Number.isInteger(saved) && saved >= 0 && saved < result.slides.length ? saved : 0)
      })
      .catch(() => { if (active) setMissing(true) })
    return () => { active = false }
  }, [publicId, retry, storageKey, targetType])

  const select = useCallback((next: number) => {
    if (!manifest?.slides.length) return
    const bounded = Math.max(0, Math.min(next, manifest.slides.length - 1))
    setPosition(bounded)
    try { sessionStorage.setItem(storageKey, String(bounded)) } catch { /* Navigation remains available. */ }
    closeNavigator()
  }, [closeNavigator, manifest, storageKey])

  useLayoutEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.defaultPrevented || ignoresShortcut(event.target) || event.altKey || event.ctrlKey || event.metaKey) return
      // OpenSeadragon does not prevent repeated keydowns for an already-held pan.
      // Keep canvas arrows with the image rather than changing the shared slide.
      if ((event.key === 'ArrowRight' || event.key === 'ArrowLeft')
        && event.target instanceof Element && event.target.closest('.openseadragon-canvas')) return
      if (event.key === 'ArrowRight') select(position + 1)
      else if (event.key === 'ArrowLeft') select(position - 1)
      else if (event.key === '+' || event.key === '=') controls.current?.zoomIn()
      else if (event.key === '-') controls.current?.zoomOut()
      else if (event.key === 'Escape') {
        if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined)
        else setDrawerOpen(false)
      }
      else return
      event.preventDefault()
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
        <Link className="share-message-return" to="/admin">Go to library</Link>
      </main>
    )
  }
  if (!manifest) {
    return <Loader label="Opening shared library…" size="large" fullscreen />
  }
  if (!manifest.slides.length) {
    return <main className="share-message"><h1>No slides are available</h1><p>This shared library is currently empty.</p></main>
  }
  const slide = manifest.slides[position]
  const filtered = manifest.slides.filter((item) => (
    `${item.displayName} ${item.organSite} ${item.stain} ${item.diagnosis}`
      .toLocaleLowerCase()
      .includes(search.toLocaleLowerCase())
  ))
  const folderTree = buildFolderTree(
    manifest.name,
    search ? [] : (manifest.folders ?? []),
    filtered,
  )
  return (
    <div className={`shared-viewer-shell ${drawerOpen ? 'drawer-open' : ''}`}>
      <header className="shared-viewer-header" aria-hidden={narrowLayout && drawerOpen || undefined} inert={narrowLayout && drawerOpen || undefined}>
        <button ref={navigatorTrigger} type="button" className="share-menu" aria-label="Open slide navigator"
          aria-controls="shared-slide-rail" aria-expanded={drawerOpen} onClick={openNavigator}><Menu /></button>
        <div><p>PathLab Viewer</p><h1 ref={headerTitle} tabIndex={-1}>{manifest.name}</h1></div>
        <ThemeControl compact className="shared-theme-control" />
        <span>{position + 1} / {manifest.slides.length}</span>
      </header>
      <button type="button" className="share-drawer-backdrop" aria-hidden="true" tabIndex={-1} inert={!drawerOpen || undefined} onClick={closeNavigator} />
      <aside
        ref={slideRail}
        id="shared-slide-rail"
        className="share-slide-rail"
        aria-label="Shared slides"
        aria-hidden={narrowLayout && !drawerOpen || undefined}
        aria-modal={narrowLayout && drawerOpen || undefined}
        role={narrowLayout && drawerOpen ? 'dialog' : undefined}
        inert={narrowLayout && !drawerOpen || undefined}
        tabIndex={-1}
      >
        <div className="share-rail-heading">
          <div><p>Teaching set</p><h2>{manifest.name}</h2></div>
          <button ref={navigatorClose} type="button" aria-label="Close slide navigator" onClick={closeNavigator}><X /></button>
        </div>
        <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search this set" aria-label="Search shared slides" />
        <div className="share-slide-list">
          {folderTree.slides.map((item) => (
            <SharedSlideButton key={item.position} item={item} position={position} select={select} />
          ))}
          {folderTree.children.map((child) => (
            <SharedFolderBranch key={child.key} node={child} position={position} select={select} />
          ))}
        </div>
      </aside>
      <main className="shared-viewer-stage" aria-hidden={narrowLayout && drawerOpen || undefined} inert={narrowLayout && drawerOpen || undefined}>
        <OpenSeadragonViewer
          tileSource={slide.tileSource}
          posterUrl={slide.thumbnailUrl}
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
