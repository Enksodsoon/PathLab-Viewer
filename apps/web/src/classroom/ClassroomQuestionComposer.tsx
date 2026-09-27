import OpenSeadragon from 'openseadragon'
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

export function ClassroomQuestionComposer({ viewer, pin, question, busy, onQuestion, onSubmit, onCancel }: {
  viewer: OpenSeadragon.Viewer
  pin: { x: number; y: number }
  question: string
  busy: boolean
  onQuestion: (value: string) => void
  onSubmit: () => void
  onCancel: () => void
}) {
  const [element] = useState(() => document.createElement('div'))
  useEffect(() => {
    element.className = 'classroom-question-composer'
    // OSD's canvas tracker otherwise captures overlay presses and consumes
    // the native click before the portal's form controls can receive it.
    const stopViewerGesture = (event: Event) => event.stopPropagation()
    const gestures = ['pointerdown', 'pointerup', 'click', 'dblclick', 'wheel']
    gestures.forEach((type) => element.addEventListener(type, stopViewerGesture))
    let placed = false
    let focusTimer: number | undefined
    const fit = () => {
      const item = viewer.world.getItemAt(0)
      if (!item || !viewer.viewport) return
      const point = viewer.viewport.pixelFromPoint(item.imageToViewportCoordinates(pin.x * item.source.dimensions.x, pin.y * item.source.dimensions.y), true)
      const bounds = viewer.container.getBoundingClientRect()
      const x = Math.max(8 - point.x, Math.min(12, bounds.width - point.x - element.offsetWidth - 8))
      const y = Math.max(8 - point.y, Math.min(12, bounds.height - point.y - element.offsetHeight - 8))
      element.style.translate = `${x}px ${y}px`
      element.style.maxHeight = `${Math.max(100, bounds.height - 16)}px`
    }
    const place = () => {
      const image = viewer.world.getItemAt(0)
      if (!image) return
      if (placed) viewer.removeOverlay(element)
      viewer.addOverlay({ element, location: image.imageToViewportCoordinates(pin.x * image.source.dimensions.x, pin.y * image.source.dimensions.y), placement: OpenSeadragon.Placement.TOP_LEFT })
      placed = true; fit()
      window.clearTimeout(focusTimer)
      focusTimer = window.setTimeout(() => { fit(); element.querySelector('textarea')?.focus({ preventScroll: true }) }, 0)
    }
    viewer.addHandler('open', place)
    viewer.addHandler('animation', fit)
    viewer.addHandler('resize', fit)
    place()
    return () => { gestures.forEach((type) => element.removeEventListener(type, stopViewerGesture)); window.clearTimeout(focusTimer); viewer.removeHandler('open', place); viewer.removeHandler('animation', fit); viewer.removeHandler('resize', fit); viewer.removeOverlay(element) }
  }, [element, viewer, pin])
  const submit = () => { if (!busy && question.trim()) onSubmit() }
  return createPortal(<form aria-label="Pinned question" onSubmit={(event) => { event.preventDefault(); submit() }}>
    <label htmlFor="classroom-pinned-question">Question at this point</label>
    <textarea id="classroom-pinned-question" maxLength={500} value={question} onChange={(event) => onQuestion(event.target.value)} onKeyDown={(event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); submit() }
      if (event.key === 'Escape' && !busy) onCancel()
    }} />
    <small>Ctrl / ⌘ Enter to send · Escape to clear</small>
    <div><button type="button" disabled={busy || !question.trim()} onClick={submit}>{busy ? 'Sending…' : 'Send question'}</button><button type="button" disabled={busy} onClick={onCancel}>Cancel</button></div>
  </form>, element)
}
