import OpenSeadragon from 'openseadragon'
import { ArrowUpRight } from '@phosphor-icons/react'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef } from 'react'

import type { TeacherPointer, TeachingAnnotation } from './api'

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
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const pointerNodeRef = useRef<HTMLSpanElement | null>(null)
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
      if (pointerNode) pointerNode.hidden = true
      return
    }
    const dimensions = item.source.dimensions
    const next = viewer.viewport.viewportToViewerElementCoordinates(
      item.imageToViewportCoordinates(visiblePointer.x * dimensions.x, visiblePointer.y * dimensions.y),
    )
    pointerNode.className = `classroom-teacher-pointer is-${visiblePointer.style}`
    pointerNode.style.transform = `translate(${next.x}px, ${next.y}px)`
    pointerNode.hidden = false
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
    const canvas = canvasRef.current
    if (!viewer || !canvas) return
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
        const bounds = canvas.getBoundingClientRect()
        const scale = Math.min(window.devicePixelRatio || 1, 2)
        canvas.width = Math.max(1, Math.round(bounds.width * scale))
        canvas.height = Math.max(1, Math.round(bounds.height * scale))
        const context = canvas.getContext('2d')
        context?.setTransform(scale, 0, 0, scale, 0, 0)
        context?.clearRect(0, 0, bounds.width, bounds.height)
        if (context) for (const annotation of visibleAnnotations) {
          const points = annotation.points.map(project)
          const first = points[0]
          const last = points.at(-1)
          if (!first || !last) continue
          context.save()
          context.strokeStyle = annotation.color
          context.lineWidth = annotation.tool === 'highlight' ? annotation.width * 4 : annotation.width
          context.lineCap = 'round'
          context.lineJoin = 'round'
          context.globalAlpha = annotation.tool === 'highlight' ? 0.42 : 1
          context.beginPath()
          if (annotation.tool === 'rectangle') {
            context.rect(first.x, first.y, last.x - first.x, last.y - first.y)
          } else if (annotation.tool === 'ellipse') {
            context.ellipse(
              (first.x + last.x) / 2,
              (first.y + last.y) / 2,
              Math.abs(last.x - first.x) / 2,
              Math.abs(last.y - first.y) / 2,
              0,
              0,
              Math.PI * 2,
            )
          } else {
            context.moveTo(first.x, first.y)
            for (const point of annotation.tool === 'line' ? [last] : points.slice(1)) {
              context.lineTo(point.x, point.y)
            }
          }
          context.stroke()
          context.restore()
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

  return <div className="classroom-teaching-overlay" aria-hidden="true">
    <canvas ref={canvasRef} data-teaching-annotations="" />
    <span
      ref={pointerNodeRef}
      data-teacher-pointer=""
      className="classroom-teacher-pointer"
      hidden
    ><ArrowUpRight aria-hidden="true" size={40} weight="bold" /></span>
  </div>
})
