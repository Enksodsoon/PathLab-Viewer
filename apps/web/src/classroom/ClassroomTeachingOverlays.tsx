import OpenSeadragon from 'openseadragon'
import { useEffect, useMemo, useRef } from 'react'

import type { TeacherPointer, TeachingAnnotation } from './api'

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
  const rootRef = useRef<SVGSVGElement | null>(null)
  const visibleAnnotations = useMemo(
    () => annotations.filter((annotation) => annotation.slideId === slideId),
    [annotations, slideId],
  )
  const visiblePointer = pointer?.slideId === slideId ? pointer : null

  useEffect(() => {
    const root = rootRef.current
    if (!viewer || !root || (!visibleAnnotations.length && !visiblePointer)) return
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
        const paths = root.querySelectorAll<SVGPathElement>('[data-teaching-stroke]')
        visibleAnnotations.forEach((annotation, annotationIndex) => {
          const points = annotation.points.map(project)
          const first = points[0]
          const last = points.at(-1)
          let data = points.map((point, index) => (
            `${index ? 'L' : 'M'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`
          )).join(' ')
          if (first && last && annotation.tool === 'line') {
            data = `M${first.x} ${first.y}L${last.x} ${last.y}`
          } else if (first && last && annotation.tool === 'rectangle') {
            data = `M${first.x} ${first.y}H${last.x}V${last.y}H${first.x}Z`
          } else if (first && last && annotation.tool === 'ellipse') {
            const cx = (first.x + last.x) / 2
            const cy = (first.y + last.y) / 2
            const rx = Math.abs(last.x - first.x) / 2
            const ry = Math.abs(last.y - first.y) / 2
            data = `M${cx - rx} ${cy}A${rx} ${ry} 0 1 0 ${cx + rx} ${cy}A${rx} ${ry} 0 1 0 ${cx - rx} ${cy}`
          }
          paths[annotationIndex]?.setAttribute('d', data)
        })
        const pointerNode = root.querySelector<SVGGElement>('[data-teacher-pointer]')
        if (pointerNode && visiblePointer) {
          const next = project(visiblePointer)
          pointerNode.setAttribute('transform', `translate(${next.x} ${next.y})`)
        }
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
  }, [viewer, visibleAnnotations, visiblePointer])

  if (!visibleAnnotations.length && !visiblePointer) return null

  return <svg ref={rootRef} className="classroom-teaching-overlay" aria-hidden="true">
    {visibleAnnotations.map((annotation) => <path
      key={annotation.id}
      data-teaching-stroke=""
      d=""
      fill="none"
      stroke={annotation.color}
      strokeWidth={annotation.tool === 'highlight' ? annotation.width * 4 : annotation.width}
      strokeLinecap="round"
      strokeLinejoin="round"
      opacity={annotation.tool === 'highlight' ? 0.42 : 1}
      vectorEffect="non-scaling-stroke"
    />)}
    {visiblePointer ? <g
      data-teacher-pointer=""
      className={`classroom-teacher-pointer is-${visiblePointer.style}`}
    ><path d="M-4 -18 L17 2 L6 5 L2 17 Z" /></g> : null}
  </svg>
}
