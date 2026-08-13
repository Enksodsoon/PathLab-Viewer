import OpenSeadragon from 'openseadragon'
import { useEffect } from 'react'

export interface ClassroomVisiblePin {
  participantId: string
  alias: string
  slideId: string
  x: number
  y: number
  focused?: boolean
}

export function ClassroomPinOverlays({
  pins,
  slideId,
  viewer,
}: {
  pins: ClassroomVisiblePin[]
  slideId: string
  viewer: OpenSeadragon.Viewer | null
}) {
  useEffect(() => {
    if (!viewer) return
    const elements: HTMLElement[] = []
    const render = () => {
      for (const element of elements.splice(0)) viewer.removeOverlay(element)
      const item = viewer.world.getItemAt(0)
      if (!item) return
      const seen = new Set<string>()
      for (const pin of pins) {
        if (pin.slideId !== slideId) continue
        const key = `${pin.participantId}:${pin.x}:${pin.y}`
        if (seen.has(key)) continue
        seen.add(key)
        const element = document.createElement('div')
        element.className = `classroom-live-pin${pin.focused ? ' is-focused' : ''}`
        element.setAttribute('aria-label', `${pin.alias} pinned this point`)
        const dot = document.createElement('span')
        const label = document.createElement('strong')
        label.textContent = pin.alias
        element.append(dot, label)
        viewer.addOverlay({
          element,
          location: item.imageToViewportCoordinates(pin.x * item.source.dimensions.x, pin.y * item.source.dimensions.y),
          placement: OpenSeadragon.Placement.BOTTOM,
        })
        elements.push(element)
      }
    }
    viewer.addHandler('open', render)
    render()
    return () => {
      viewer.removeHandler('open', render)
      for (const element of elements) viewer.removeOverlay(element)
    }
  }, [pins, slideId, viewer])

  return null
}
