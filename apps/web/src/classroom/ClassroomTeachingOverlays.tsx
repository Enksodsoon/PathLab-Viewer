import OpenSeadragon from 'openseadragon'
import { useEffect, useState } from 'react'

import type { TeacherPointer, TeachingAnnotation } from './api'

interface ProjectedAnnotation extends TeachingAnnotation {
  path: string
}

export function ClassroomTeachingOverlays({
  annotations,
  pointer,
  slideId,
  viewer,
}: {
  annotations: TeachingAnnotation[]
  pointer: TeacherPointer | null
  slideId: string
  viewer: OpenSeadragon.Viewer | null
}) {
  const [projected, setProjected] = useState<ProjectedAnnotation[]>([])
  const [pointerPoint, setPointerPoint] = useState<{ x: number; y: number } | null>(null)

  useEffect(() => {
    if (!viewer) return
    let frame: number | null = null
    const render = () => {
      if (frame !== null) return
      frame = window.requestAnimationFrame(() => {
        frame = null
        const item = viewer.world.getItemAt(0)
        if (!item) return
        const dimensions = item.source.dimensions
        const project = (point: { x: number; y: number }) => (
          viewer.viewport.viewportToViewerElementCoordinates(
            item.imageToViewportCoordinates(point.x * dimensions.x, point.y * dimensions.y),
          )
        )
        setProjected(annotations.filter((annotation) => annotation.slideId === slideId).map((annotation) => ({
          ...annotation,
          path: annotation.points.map((point, index) => {
            const next = project(point)
            return `${index ? 'L' : 'M'}${next.x.toFixed(1)} ${next.y.toFixed(1)}`
          }).join(' '),
        })))
        setPointerPoint(pointer?.slideId === slideId ? project(pointer) : null)
      })
    }
    viewer.addHandler('open', render)
    viewer.addHandler('animation', render)
    viewer.addHandler('animation-finish', render)
    const observer = new ResizeObserver(render)
    observer.observe(viewer.container)
    render()
    return () => {
      viewer.removeHandler('open', render)
      viewer.removeHandler('animation', render)
      viewer.removeHandler('animation-finish', render)
      observer.disconnect()
      if (frame !== null) window.cancelAnimationFrame(frame)
    }
  }, [annotations, pointer, slideId, viewer])

  return <svg className="classroom-teaching-overlay" aria-hidden="true">
    {projected.map((annotation) => <path
      key={annotation.id}
      d={annotation.path}
      fill="none"
      stroke={annotation.color}
      strokeWidth={annotation.tool === 'highlight' ? annotation.width * 4 : annotation.width}
      strokeLinecap="round"
      strokeLinejoin="round"
      opacity={annotation.tool === 'highlight' ? 0.42 : 1}
      vectorEffect="non-scaling-stroke"
    />)}
    {pointerPoint && pointer ? <g
      className={`classroom-teacher-pointer is-${pointer.style}`}
      transform={`translate(${pointerPoint.x} ${pointerPoint.y})`}
    >{pointer.style === 'laser'
        ? <><circle r="13" /><circle className="core" r="4" /></>
        : <path d="M-4 -18 L17 2 L6 5 L2 17 Z" />}</g> : null}
  </svg>
}
