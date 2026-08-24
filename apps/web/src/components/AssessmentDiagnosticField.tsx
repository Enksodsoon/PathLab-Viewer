import { Crosshair, Hand, Rectangle } from '@phosphor-icons/react'
import OpenSeadragon from 'openseadragon'
import { useCallback, useRef, useState } from 'react'

import type { DiagnosticSelection } from '../assessment/types'
import { OpenSeadragonViewer, type ViewerAttachmentCallback } from './OpenSeadragonViewer'

interface Props {
  tileSource: string
  selections: DiagnosticSelection[]
  onCommit: (selection: DiagnosticSelection) => void
  onClear?: () => void
  multiple?: boolean
  label: string
}

function clamp(value: number) {
  return Math.max(0, Math.min(1, value))
}

export function AssessmentDiagnosticField({
  tileSource,
  selections,
  onCommit,
  onClear,
  multiple = false,
  label,
}: Props) {
  const [tool, setTool] = useState<'pan' | 'point' | 'rectangle'>('pan')
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)
  const commitAtViewportPoint = useCallback((viewportPoint: OpenSeadragon.Point, rectangle = false) => {
    const tiledImage = viewerRef.current?.world.getItemAt(0)
    if (!tiledImage) return
    const imagePoint = tiledImage.viewportToImageCoordinates(viewportPoint)
    const size = tiledImage.getContentSize()
    const x = clamp(imagePoint.x / size.x)
    const y = clamp(imagePoint.y / size.y)
    onCommit(rectangle
      ? { kind: 'rectangle', x: clamp(x - 0.05), y: clamp(y - 0.05), width: 0.1, height: 0.1 }
      : { kind: 'point', x, y })
  }, [onCommit])

  const attach = useCallback<ViewerAttachmentCallback>((viewer) => {
    viewerRef.current = viewer
    viewer.setMouseNavEnabled(tool === 'pan')
    const overlays: HTMLElement[] = []
    const tiledImage = viewer.world.getItemAt(0)
    if (tiledImage) {
      const size = tiledImage.getContentSize()
      selections.forEach((selection, index) => {
        const element = document.createElement('div')
        element.className = selection.kind === 'point'
          ? 'assessment-diagnostic-point'
          : 'assessment-diagnostic-rectangle'
        element.setAttribute('aria-hidden', 'true')
        const imageRect = selection.kind === 'point'
          ? new OpenSeadragon.Rect(selection.x * size.x - 8, selection.y * size.y - 8, 16, 16)
          : new OpenSeadragon.Rect(
            selection.x * size.x,
            selection.y * size.y,
            selection.width * size.x,
            selection.height * size.y,
          )
        viewer.addOverlay({
          element,
          location: tiledImage.imageToViewportRectangle(imageRect),
          checkResize: false,
        })
        element.dataset.selectionIndex = String(index)
        overlays.push(element)
      })
    }
    const tracker = new OpenSeadragon.MouseTracker({
      element: viewer.canvas,
      clickHandler: (event) => {
        if (tool === 'pan' || !event.quick) return
        commitAtViewportPoint(viewer.viewport.pointFromPixel(event.position), tool === 'rectangle')
      },
    })
    tracker.setTracking(true)
    return () => {
      tracker.destroy()
      overlays.forEach((element) => viewer.removeOverlay(element))
      viewer.setMouseNavEnabled(true)
      if (viewerRef.current === viewer) viewerRef.current = null
    }
  }, [commitAtViewportPoint, selections, tool])

  function commitAtCenter() {
    const viewer = viewerRef.current
    if (!viewer || tool === 'pan') return
    commitAtViewportPoint(viewer.viewport.getCenter(), tool === 'rectangle')
  }

  return <section className="assessment-diagnostic-workspace" aria-label={label}>
    <div className="assessment-diagnostic-toolbar" role="toolbar" aria-label="Slide selection tools">
      <button type="button" aria-pressed={tool === 'pan'} onClick={() => setTool('pan')}>
        <Hand aria-hidden="true" /> Pan / zoom
      </button>
      <button type="button" aria-pressed={tool === 'point'} onClick={() => setTool('point')}>
        <Crosshair aria-hidden="true" /> Point
      </button>
      <button type="button" aria-pressed={tool === 'rectangle'} onClick={() => setTool('rectangle')}>
        <Rectangle aria-hidden="true" /> Rectangle
      </button>
      <button type="button" disabled={tool === 'pan'} onClick={commitAtCenter}>
        Place at viewport center
      </button>
      {onClear ? <button type="button" disabled={selections.length === 0} onClick={onClear}>
        Clear selection{multiple ? 's' : ''}
      </button> : null}
    </div>
    <div className="assessment-diagnostic-viewer">
      <OpenSeadragonViewer tileSource={tileSource} onReady={() => undefined} onViewerAttach={attach} />
    </div>
    <p role="status">{selections.length} committed selection{selections.length === 1 ? '' : 's'}.</p>
  </section>
}
