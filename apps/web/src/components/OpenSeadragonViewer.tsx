import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import OpenSeadragon from 'openseadragon'

import {
  initialViewerNetworkState,
  nextViewerNetworkState,
  type ViewerConnectionHint,
  type ViewerLoadingMode,
} from '../viewerNetwork'

const NARROW_VIEWPORT_MAX = 768
const TILE_FAILURE_LIMIT = 3
const NETWORK_MODE_KEY = 'pathlab-viewer-loading-mode:v1'
const NETWORK_WINDOW_MS = 5000
const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 15000]

export interface ViewerHandle {
  zoomIn: () => void
  zoomOut: () => void
  home: () => void
  rotate: () => void
  fullscreen: () => void
}

export type ViewerAttachmentCallback = (
  viewer: OpenSeadragon.Viewer,
) => void | (() => void)

interface Props {
  tileSource: string
  posterUrl?: string | null
  onReady: (handle: ViewerHandle) => void
  micronsPerPixel?: number | null
  onScaleChange?: (microns: number, width: number) => void
  onViewerAttach?: ViewerAttachmentCallback
}

interface NavigatorWithConnection extends Navigator {
  connection?: ViewerConnectionHint
}

function savedLoadingMode(): ViewerLoadingMode {
  const saved = localStorage.getItem(NETWORK_MODE_KEY)
  return saved === 'data-saver' || saved === 'full' ? saved : 'auto'
}

function niceScale(value: number) {
  const exponent = 10 ** Math.floor(Math.log10(value))
  const normalized = value / exponent
  return (normalized < 2 ? 1 : normalized < 5 ? 2 : 5) * exponent
}

export function OpenSeadragonViewer({
  tileSource,
  posterUrl,
  onReady,
  micronsPerPixel,
  onScaleChange,
  onViewerAttach,
}: Props) {
  const element = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)
  const tileSourceRef = useRef(tileSource)
  const openedSourceRef = useRef(tileSource)
  const onReadyRef = useRef(onReady)
  const modeRef = useRef<ViewerLoadingMode>('auto')
  const micronsPerPixelRef = useRef(micronsPerPixel)
  const onScaleChangeRef = useRef(onScaleChange)
  const attachmentCallbackRef = useRef(onViewerAttach)
  const attachmentCleanupRef = useRef<(() => void) | null>(null)
  const tileFailures = useRef(0)
  const windowFailures = useRef(0)
  const errorTimer = useRef<number | null>(null)
  const reconnectTimer = useRef<number | null>(null)
  const reconnectAttempt = useRef(0)
  const [mode, setMode] = useState<ViewerLoadingMode>(savedLoadingMode)
  const [posterVisible, setPosterVisible] = useState(Boolean(posterUrl))
  const [connectionStatus, setConnectionStatus] = useState<string | null>(null)
  const [loadingError, setLoadingError] = useState(false)
  const [rotation, setRotation] = useState(0)
  const [rotationOpen, setRotationOpen] = useState(false)
  const rotationControl = useRef<HTMLDivElement>(null)
  const rotationPointer = useRef<number | null>(null)
  const narrowViewport = window.innerWidth < NARROW_VIEWPORT_MAX
  const networkState = useRef(initialViewerNetworkState(
    mode,
    narrowViewport,
    (navigator as NavigatorWithConnection).connection,
  ))
  const retryLoading = useCallback(() => {
    if (errorTimer.current !== null) {
      window.clearTimeout(errorTimer.current)
      errorTimer.current = null
    }
    tileFailures.current = 0
    setLoadingError(false)
    viewerRef.current?.open(tileSourceRef.current as unknown as OpenSeadragon.TileSourceSpecifier)
  }, [])
  const applyRotation = useCallback((degrees: number) => {
    const viewer = viewerRef.current
    if (!viewer) return
    const normalized = ((degrees % 360) + 360) % 360
    viewer.viewport.setRotation(degrees === 360 ? 360 : normalized)
    setRotation(degrees === 360 ? 360 : normalized)
  }, [])
  const rotateFromPointer = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect()
    const horizontal = event.clientX - (bounds.left + bounds.width / 2)
    const vertical = event.clientY - (bounds.top + bounds.height / 2)
    const degrees = Math.round((Math.atan2(horizontal, -vertical) * 180 / Math.PI + 360) % 360)
    applyRotation(degrees)
  }, [applyRotation])
  useEffect(() => {
    if (!rotationOpen) return
    const closeOnOutsidePress = (event: PointerEvent) => {
      if (!rotationControl.current?.contains(event.target as Node)) setRotationOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setRotationOpen(false)
    }
    document.addEventListener('pointerdown', closeOnOutsidePress)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePress)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [rotationOpen])
  const detachViewerAttachment = useCallback(() => {
    const cleanup = attachmentCleanupRef.current
    attachmentCleanupRef.current = null
    try {
      cleanup?.()
    } catch {
      // An optional overlay must never block source replacement or viewer cleanup.
    }
  }, [])
  const attachViewerAttachment = useCallback((viewer: OpenSeadragon.Viewer) => {
    const callback = attachmentCallbackRef.current
    if (!callback) return
    try {
      attachmentCleanupRef.current = callback(viewer) ?? null
    } catch {
      viewer.setMouseNavEnabled?.(true)
      attachmentCleanupRef.current = null
    }
  }, [])
  useEffect(() => {
    tileSourceRef.current = tileSource
    onReadyRef.current = onReady
    micronsPerPixelRef.current = micronsPerPixel
    onScaleChangeRef.current = onScaleChange
    if (viewerRef.current && openedSourceRef.current !== tileSource) {
      openedSourceRef.current = tileSource
      tileFailures.current = 0
      setPosterVisible(Boolean(posterUrl))
      setLoadingError(false)
      detachViewerAttachment()
      viewerRef.current.open(tileSource as unknown as OpenSeadragon.TileSourceSpecifier)
      attachViewerAttachment(viewerRef.current)
      if (reconnectTimer.current !== null) {
        window.clearTimeout(reconnectTimer.current)
        reconnectTimer.current = null
      }
      reconnectAttempt.current = 0
    }
  }, [
    attachViewerAttachment,
    detachViewerAttachment,
    micronsPerPixel,
    onReady,
    onScaleChange,
    posterUrl,
    tileSource,
  ])
  useEffect(() => {
    attachmentCallbackRef.current = onViewerAttach
    const viewer = viewerRef.current
    if (!viewer) return
    detachViewerAttachment()
    attachViewerAttachment(viewer)
  }, [attachViewerAttachment, detachViewerAttachment, onViewerAttach])
  useEffect(() => {
    modeRef.current = mode
    localStorage.setItem(NETWORK_MODE_KEY, mode)
    const next = initialViewerNetworkState(
      mode,
      narrowViewport,
      mode === 'auto' ? (navigator as NavigatorWithConnection).connection : undefined,
    )
    networkState.current = next
    if (viewerRef.current) viewerRef.current.imageLoader.jobLimit = next.jobLimit
  }, [mode, narrowViewport])
  useEffect(() => {
    if (!element.current) return
    let viewer: OpenSeadragon.Viewer | null = null
    let disposed = false
    const mountedNarrowViewport = window.innerWidth < NARROW_VIEWPORT_MAX
    const durations: number[] = []
    let performanceObserver: PerformanceObserver | null = null
    let networkTimer: number | null = null
    const scheduleReconnect = (overrideDelay?: number) => {
      if (disposed || reconnectTimer.current !== null || !navigator.onLine) return
      const index = Math.min(reconnectAttempt.current, RECONNECT_DELAYS_MS.length - 1)
      const delay = overrideDelay ?? RECONNECT_DELAYS_MS[index]
      reconnectAttempt.current += 1
      setConnectionStatus('Reconnecting…')
      reconnectTimer.current = window.setTimeout(() => {
        reconnectTimer.current = null
        if (!disposed && navigator.onLine) {
          viewerRef.current?.open(tileSourceRef.current as unknown as OpenSeadragon.TileSourceSpecifier)
        }
      }, delay)
    }
    const handleOffline = () => {
      if (reconnectTimer.current !== null) {
        window.clearTimeout(reconnectTimer.current)
        reconnectTimer.current = null
      }
      networkState.current = { jobLimit: 2, healthyWindows: 0 }
      if (viewerRef.current) viewerRef.current.imageLoader.jobLimit = 2
      setConnectionStatus('Offline — keeping the current view')
    }
    const handleOnline = () => {
      setConnectionStatus('Connection restored')
      if (reconnectAttempt.current > 0) scheduleReconnect(500 + Math.random() * 2000)
    }
    const clearLoadingError = () => {
      if (errorTimer.current !== null) {
        window.clearTimeout(errorTimer.current)
        errorTimer.current = null
      }
      tileFailures.current = 0
      setLoadingError(false)
    }
    const reportLoadingError = () => {
      if (disposed || errorTimer.current !== null) return
      errorTimer.current = window.setTimeout(() => {
        errorTimer.current = null
        if (!disposed) setLoadingError(true)
      }, 0)
    }
    window.addEventListener('offline', handleOffline)
    window.addEventListener('online', handleOnline)
    try {
      viewer = OpenSeadragon({
        element: element.current,
        tileSources: tileSourceRef.current,
        showNavigationControl: false,
        showNavigator: !mountedNarrowViewport,
        navigatorPosition: 'BOTTOM_RIGHT',
        navigatorSizeRatio: 0.16,
        navigatorMaintainSizeRatio: true,
        animationTime: 0.45,
        blendTime: 0.05,
        constrainDuringPan: true,
        maxZoomPixelRatio: 2,
        visibilityRatio: 0.5,
        imageLoaderLimit: networkState.current.jobLimit,
        maxImageCacheCount: mountedNarrowViewport ? 50 : 100,
        tileRetryMax: 1,
        tileRetryDelay: 1000,
        timeout: 20000,
        gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true, flickEnabled: true },
        gestureSettingsTouch: { pinchToZoom: true, flickEnabled: true },
      })
      viewerRef.current = viewer
      attachViewerAttachment(viewer)
      onReadyRef.current({
        zoomIn: () => viewer?.viewport.zoomBy(1.5),
        zoomOut: () => viewer?.viewport.zoomBy(1 / 1.5),
        home: () => viewer?.viewport.goHome(),
        rotate: () => {
          if (!viewer) return
          const next = (viewer.viewport.getRotation() + 90) % 360
          applyRotation(next)
        },
        fullscreen: () => void viewer?.setFullScreen(!viewer.isFullPage()),
      })
      const updateScale = () => {
        const scale = micronsPerPixelRef.current
        const reportScale = onScaleChangeRef.current
        if (!viewer || !scale || !reportScale) return
        const imageZoom = viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom(true))
        const micronsPerScreenPixel = scale / imageZoom
        const microns = niceScale(micronsPerScreenPixel * 90)
        reportScale(microns, microns / micronsPerScreenPixel)
      }
      const handleOpen = () => {
        if (reconnectTimer.current !== null) {
          window.clearTimeout(reconnectTimer.current)
          reconnectTimer.current = null
        }
        reconnectAttempt.current = 0
        setConnectionStatus(null)
        clearLoadingError()
        updateScale()
      }
      const handleTileLoaded = () => setPosterVisible(false)
      const handleTileLoadFailed = () => {
        windowFailures.current += 1
        if (tileFailures.current >= TILE_FAILURE_LIMIT) return
        tileFailures.current += 1
        if (tileFailures.current === TILE_FAILURE_LIMIT) reportLoadingError()
      }
      viewer.addHandler('open', handleOpen)
      viewer.addHandler('tile-loaded', handleTileLoaded)
      viewer.addHandler('animation-finish', updateScale)
      viewer.addHandler('open-failed', () => {
        reportLoadingError()
        scheduleReconnect()
      })
      viewer.addHandler('tile-load-failed', handleTileLoadFailed)

      if (typeof PerformanceObserver !== 'undefined') {
        performanceObserver = new PerformanceObserver((list) => {
          for (const entry of list.getEntries() as PerformanceResourceTiming[]) {
            if (!entry.name.includes('/tiles/') || entry.transferSize === 0) continue
            durations.push(entry.duration)
          }
        })
        try {
          performanceObserver.observe({ type: 'resource', buffered: true })
        } catch {
          performanceObserver = null
        }
      }
      networkTimer = window.setInterval(() => {
        const sorted = durations.splice(0).sort((left, right) => left - right)
        const failures = windowFailures.current
        windowFailures.current = 0
        const sampleCount = sorted.length + failures
        const p75Index = Math.max(0, Math.ceil(sorted.length * 0.75) - 1)
        networkState.current = nextViewerNetworkState(networkState.current, {
          online: navigator.onLine,
          sampleCount,
          failureRate: sampleCount ? failures / sampleCount : 0,
          p75Ms: sorted[p75Index] ?? 0,
        }, mountedNarrowViewport, modeRef.current)
        if (viewer) viewer.imageLoader.jobLimit = networkState.current.jobLimit
      }, NETWORK_WINDOW_MS)
    } catch {
      reportLoadingError()
    }
    return () => {
      disposed = true
      detachViewerAttachment()
      if (errorTimer.current !== null) {
        window.clearTimeout(errorTimer.current)
        errorTimer.current = null
      }
      if (reconnectTimer.current !== null) {
        window.clearTimeout(reconnectTimer.current)
        reconnectTimer.current = null
      }
      if (networkTimer !== null) window.clearInterval(networkTimer)
      performanceObserver?.disconnect()
      window.removeEventListener('offline', handleOffline)
      window.removeEventListener('online', handleOnline)
      viewer?.removeAllHandlers('open')
      viewer?.removeAllHandlers('tile-loaded')
      viewer?.removeAllHandlers('animation-finish')
      viewer?.removeAllHandlers('open-failed')
      viewer?.removeAllHandlers('tile-load-failed')
      viewer?.destroy()
      if (viewerRef.current === viewer) viewerRef.current = null
    }
  }, [applyRotation, attachViewerAttachment, detachViewerAttachment])
  return <div className="osd-surface" data-tile-source={tileSource} style={{ position: 'relative' }}>
    {posterVisible && posterUrl ? <img
      className="viewer-poster"
      src={posterUrl}
      alt="Slide preview"
      fetchPriority="high"
      decoding="async"
    /> : null}
    <div ref={element} style={{ position: 'absolute', inset: 0 }} />
    <label className="viewer-loading-mode">
      <span>Loading</span>
      <select aria-label="Loading mode" value={mode} onChange={(event) => setMode(event.target.value as ViewerLoadingMode)}>
        <option value="auto">Auto</option>
        <option value="data-saver">Data saver</option>
        <option value="full">Full detail</option>
      </select>
    </label>
    <div className="viewer-rotation" ref={rotationControl}>
      <button
        className="viewer-rotation-control"
        type="button"
        aria-label={`Open rotation controls. Current rotation ${rotation} degrees`}
        aria-expanded={rotationOpen}
        title={`Rotation · ${rotation}°`}
        onClick={() => setRotationOpen((open) => !open)}
      >
        <span>{rotation}°</span>
      </button>
      {rotationOpen ? <div className="viewer-rotation-popover" role="dialog" aria-label="Slide rotation">
        <div
          className="viewer-rotation-dial"
          role="slider"
          tabIndex={0}
          aria-label="Rotation dial"
          aria-valuemin={0}
          aria-valuemax={359}
          aria-valuenow={rotation === 360 ? 0 : rotation}
          aria-valuetext={`${rotation} degrees`}
          onKeyDown={(event) => {
            if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
              event.preventDefault()
              applyRotation(rotation - 1)
            } else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
              event.preventDefault()
              applyRotation(rotation + 1)
            } else if (event.key === 'Home') {
              event.preventDefault()
              applyRotation(0)
            }
          }}
          onPointerDown={(event) => {
            rotationPointer.current = event.pointerId
            event.currentTarget.setPointerCapture(event.pointerId)
            rotateFromPointer(event)
          }}
          onPointerMove={(event) => {
            if (rotationPointer.current === event.pointerId) rotateFromPointer(event)
          }}
          onPointerUp={(event) => {
            if (rotationPointer.current !== event.pointerId) return
            rotateFromPointer(event)
            rotationPointer.current = null
            event.currentTarget.releasePointerCapture(event.pointerId)
          }}
          onPointerCancel={() => { rotationPointer.current = null }}
        >
          <div className="viewer-rotation-ticks" aria-hidden="true" />
          {[0, 90, 180, 270].map((degrees) => <button
            key={degrees}
            type="button"
            className={`viewer-rotation-cardinal is-${degrees}`}
            aria-label={`Rotate to ${degrees} degrees`}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => applyRotation(degrees)}
          >{degrees === 270 ? '270' : degrees}</button>)}
          <div className="viewer-rotation-needle" aria-hidden="true" style={{ transform: `rotate(${rotation}deg)` }}>
            <i />
          </div>
          <output aria-live="polite">{rotation}°</output>
        </div>
      </div> : null}
    </div>
    {connectionStatus ? <div className="viewer-connection-status" role="status">{connectionStatus}</div> : null}
    {loadingError ? <div
      role="alert"
      style={{
        position: 'absolute', left: 12, bottom: 12, zIndex: 2, maxWidth: 260,
        padding: '10px 12px', borderRadius: 8, background: 'rgba(20, 27, 33, 0.92)',
        color: '#fff', fontSize: 13, boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
      }}
    >
      <span>Slide tiles could not be loaded.</span>{' '}
      <button type="button" onClick={retryLoading} style={{ marginLeft: 6 }}>Retry loading</button>
    </div> : null}
  </div>
}
