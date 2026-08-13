import OpenSeadragon from 'openseadragon'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef } from 'react'

import type { TeacherPointer, TeachingAnnotation } from './api'

function normalizedPath(annotation: TeachingAnnotation): string {
  const points = annotation.points.map((point) => ({ x: point.x * 100, y: point.y * 100 }))
  const first = points[0]
  const last = points.at(-1)
  if (!first || !last) return ''
  if (annotation.tool === 'line') return `M${first.x} ${first.y}L${last.x} ${last.y}`
  if (annotation.tool === 'rectangle') return `M${first.x} ${first.y}H${last.x}V${last.y}H${first.x}Z`
  if (annotation.tool === 'ellipse') {
    const cx = (first.x + last.x) / 2
    const cy = (first.y + last.y) / 2
    const rx = Math.abs(last.x - first.x) / 2
    const ry = Math.abs(last.y - first.y) / 2
    return `M${cx - rx} ${cy}A${rx} ${ry} 0 1 0 ${cx + rx} ${cy}A${rx} ${ry} 0 1 0 ${cx - rx} ${cy}`
  }
  return points.map((point, index) => `${index ? 'L' : 'M'}${point.x} ${point.y}`).join(' ')
}

export interface ClassroomTeachingOverlayHandle {
  setPointer: (pointer: TeacherPointer | null) => void
}

export const ClassroomTeachingOverlays = forwardRef<ClassroomTeachingOverlayHandle, {
  annotations: TeachingAnnotation[]
  pointer: TeacherPointer | null
  slideId: string
  viewer: OpenSeadragon.Viewer | null
}>(function ClassroomTeachingOverlays({
  annotations,
  pointer,
  slideId,
  viewer,
}, ref) {
  const rootRef = useRef<SVGSVGElement | null>(null)
  const annotationLayerRef = useRef<SVGGElement | null>(null)
  const pointerNodeRef = useRef<SVGGElement | null>(null)
  const pointerRef = useRef<TeacherPointer | null>(pointer)
  const pointerFrameRef = useRef<number | null>(null)
  const visibleAnnotations = useMemo(
    () => annotations.filter((annotation) => annotation.slideId === slideId),
    [annotations, slideId],
  )
  const projectPointer = useCallback(() => {
    const visiblePointer = pointerRef.current?.slideId === slideId ? pointerRef.current : null
    const pointerNode = pointerNodeRef.current
    const item = viewer?.world.getItemAt(0)
    if (!pointerNode || !viewer || !item || !visiblePointer) {
      pointerNode?.setAttribute('visibility', 'hidden')
      return
    }
    const dimensions = item.source.dimensions
    const next = viewer.viewport.viewportToViewerElementCoordinates(
      item.imageToViewportCoordinates(visiblePointer.x * dimensions.x, visiblePointer.y * dimensions.y),
    )
    pointerNode.setAttribute('class', `classroom-teacher-pointer is-${visiblePointer.style}`)
    pointerNode.setAttribute('transform', `translate(${next.x} ${next.y})`)
    pointerNode.setAttribute('visibility', 'visible')
  }, [slideId, viewer])

  const schedulePointerProjection = useCallback(() => {
    if (pointerFrameRef.current !== null) return
    pointerFrameRef.current = window.requestAnimationFrame(() => {
      pointerFrameRef.current = null
      projectPointer()
    })
  }, [projectPointer])

  useImperativeHandle(ref, () => ({
    setPointer(next) {
      pointerRef.current = next
      schedulePointerProjection()
    },
  }), [schedulePointerProjection])

  useEffect(() => {
    pointerRef.current = pointer
    schedulePointerProjection()
  }, [pointer, schedulePointerProjection])

  useEffect(() => () => {
    if (pointerFrameRef.current !== null) window.cancelAnimationFrame(pointerFrameRef.current)
  }, [])

  useEffect(() => {
    const root = rootRef.current
    if (!viewer || !root) return
    let frame: number | null = null
    const render = () => {
      if (!visibleAnnotations.length && pointerRef.current?.slideId !== slideId) return
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
        const annotationLayer = annotationLayerRef.current
        if (annotationLayer && visibleAnnotations.length) {
          const origin = project({ x: 0, y: 0 })
          const horizontal = project({ x: 1, y: 0 })
          const vertical = project({ x: 0, y: 1 })
          annotationLayer.setAttribute('transform', `matrix(${(horizontal.x - origin.x) / 100} ${(horizontal.y - origin.y) / 100} ${(vertical.x - origin.x) / 100} ${(vertical.y - origin.y) / 100} ${origin.x} ${origin.y})`)
        }
        projectPointer()
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
  }, [viewer, visibleAnnotations, projectPointer, slideId])

  return <svg ref={rootRef} className="classroom-teaching-overlay" aria-hidden="true">
    <g ref={annotationLayerRef} data-teaching-annotations="">{visibleAnnotations.map((annotation) => <path
        key={annotation.id}
        data-teaching-stroke=""
        d={normalizedPath(annotation)}
        fill="none"
        stroke={annotation.color}
        strokeWidth={annotation.tool === 'highlight' ? annotation.width * 4 : annotation.width}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={annotation.tool === 'highlight' ? 0.42 : 1}
        vectorEffect="non-scaling-stroke"
      />)}</g>
    <g
      ref={pointerNodeRef}
      data-teacher-pointer=""
      className="classroom-teacher-pointer"
      visibility="hidden"
    ><path d="M4 38 36 6M17 6h19v19" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" /></g>
  </svg>
})
