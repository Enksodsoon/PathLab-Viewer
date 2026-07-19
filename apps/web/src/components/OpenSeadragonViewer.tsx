import { useEffect, useRef } from 'react'
import OpenSeadragon from 'openseadragon'

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
  useEffect(() => {
    if (!element.current) return
    let viewer: OpenSeadragon.Viewer | null = null
    try {
      viewer = OpenSeadragon({
        element: element.current,
        tileSources: tileSource,
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
        gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true, flickEnabled: true },
        gestureSettingsTouch: { pinchToZoom: true, flickEnabled: true },
      })
      onReady({
        zoomIn: () => viewer?.viewport.zoomBy(1.5),
        zoomOut: () => viewer?.viewport.zoomBy(1 / 1.5),
        home: () => viewer?.viewport.goHome(),
        fullscreen: () => void viewer?.setFullScreen(!viewer.isFullPage()),
      })
      const updateScale = () => {
        if (!viewer || !micronsPerPixel || !onScaleChange) return
        const imageZoom = viewer.viewport.viewportToImageZoom(viewer.viewport.getZoom(true))
        const micronsPerScreenPixel = micronsPerPixel / imageZoom
        const microns = niceScale(micronsPerScreenPixel * 90)
        onScaleChange(microns, microns / micronsPerScreenPixel)
      }
      viewer.addHandler('open', updateScale)
      viewer.addHandler('animation', updateScale)
    } catch {
      // The viewer surface remains available while a tile/network error is reported by the browser.
    }
    return () => viewer?.destroy()
  }, [micronsPerPixel, onReady, onScaleChange, tileSource])
  return <div className="osd-surface" ref={element} data-tile-source={tileSource} />
}
