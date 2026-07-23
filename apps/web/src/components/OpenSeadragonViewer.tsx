import { useCallback, useEffect, useRef, useState } from 'react'
import OpenSeadragon from 'openseadragon'

const NARROW_VIEWPORT_MAX = 768
const TILE_FAILURE_LIMIT = 3

export interface ViewerHandle {
  zoomIn: () => void
  zoomOut: () => void
  home: () => void
  fullscreen: () => void
}

interface Props {
  tileSource: string
  onReady: (handle: ViewerHandle) => void
  micronsPerPixel?: number | null
  onScaleChange?: (microns: number, width: number) => void
}

function niceScale(value: number) {
  const exponent = 10 ** Math.floor(Math.log10(value))
  const normalized = value / exponent
  return (normalized < 2 ? 1 : normalized < 5 ? 2 : 5) * exponent
}

export function OpenSeadragonViewer({ tileSource, onReady, micronsPerPixel, onScaleChange }: Props) {
  const element = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)
  const tileSourceRef = useRef(tileSource)
  const openedSourceRef = useRef(tileSource)
  const onReadyRef = useRef(onReady)
  const micronsPerPixelRef = useRef(micronsPerPixel)
  const onScaleChangeRef = useRef(onScaleChange)
  const tileFailures = useRef(0)
  const errorTimer = useRef<number | null>(null)
  const [loadingError, setLoadingError] = useState(false)
  const retryLoading = useCallback(() => {
    if (errorTimer.current !== null) {
      window.clearTimeout(errorTimer.current)
      errorTimer.current = null
    }
    tileFailures.current = 0
    setLoadingError(false)
    viewerRef.current?.open(tileSourceRef.current as unknown as OpenSeadragon.TileSourceSpecifier)
  }, [])
  useEffect(() => {
    tileSourceRef.current = tileSource
    onReadyRef.current = onReady
    micronsPerPixelRef.current = micronsPerPixel
    onScaleChangeRef.current = onScaleChange
    if (viewerRef.current && openedSourceRef.current !== tileSource) {
      openedSourceRef.current = tileSource
      tileFailures.current = 0
      setLoadingError(false)
      viewerRef.current.open(tileSource as unknown as OpenSeadragon.TileSourceSpecifier)
    }
  }, [micronsPerPixel, onReady, onScaleChange, tileSource])
  useEffect(() => {
    if (!element.current) return
    let viewer: OpenSeadragon.Viewer | null = null
    let disposed = false
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
    try {
      const narrowViewport = window.innerWidth < NARROW_VIEWPORT_MAX
      viewer = OpenSeadragon({
        element: element.current,
        tileSources: tileSourceRef.current,
        showNavigationControl: false,
        showNavigator: true,
        navigatorPosition: 'BOTTOM_RIGHT',
        navigatorSizeRatio: 0.16,
        navigatorMaintainSizeRatio: true,
        animationTime: 0.75,
        blendTime: 0.1,
        constrainDuringPan: true,
        maxZoomPixelRatio: 2,
        visibilityRatio: 0.5,
        imageLoaderLimit: narrowViewport ? 6 : 10,
        maxImageCacheCount: narrowViewport ? 50 : 100,
        tileRetryMax: 2,
        tileRetryDelay: 500,
        timeout: 20000,
        gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true, flickEnabled: true },
        gestureSettingsTouch: { pinchToZoom: true, flickEnabled: true },
      })
      viewerRef.current = viewer
      onReadyRef.current({
        zoomIn: () => viewer?.viewport.zoomBy(1.5),
        zoomOut: () => viewer?.viewport.zoomBy(1 / 1.5),
        home: () => viewer?.viewport.goHome(),
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
        clearLoadingError()
        updateScale()
      }
      const handleTileLoadFailed = () => {
        if (tileFailures.current >= TILE_FAILURE_LIMIT) return
        tileFailures.current += 1
        if (tileFailures.current === TILE_FAILURE_LIMIT) reportLoadingError()
      }
      viewer.addHandler('open', handleOpen)
      viewer.addHandler('animation-finish', updateScale)
      viewer.addHandler('open-failed', reportLoadingError)
      viewer.addHandler('tile-load-failed', handleTileLoadFailed)
    } catch {
      reportLoadingError()
    }
    return () => {
      disposed = true
      if (errorTimer.current !== null) {
        window.clearTimeout(errorTimer.current)
        errorTimer.current = null
      }
      viewer?.removeAllHandlers('open')
      viewer?.removeAllHandlers('animation-finish')
      viewer?.removeAllHandlers('open-failed')
      viewer?.removeAllHandlers('tile-load-failed')
      viewer?.destroy()
      if (viewerRef.current === viewer) viewerRef.current = null
    }
  }, [])
  return <div className="osd-surface" data-tile-source={tileSource} style={{ position: 'relative' }}>
    <div ref={element} style={{ position: 'absolute', inset: 0 }} />
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
